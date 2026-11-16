import os
import re
import subprocess
import sysconfig
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from typer.testing import CliRunner

from frameread.cli.main import app
from frameread.db.engine import make_async_engine
from frameread.db.models import instance_state, resource_slots, tasks
from frameread.services.admission import AdmissionRequest, submit_admission

from . import test_admin_sessions
from .conftest import ROOT_KEY

pytestmark = pytest.mark.integration

ORIGIN = test_admin_sessions.ORIGIN
admin_env = test_admin_sessions.admin_env
login = test_admin_sessions.login
session_app = test_admin_sessions.session_app
runner = CliRunner()


@pytest.fixture
def cli_env(migrated_db, tmp_path: Path, monkeypatch):
    dsn_file = tmp_path / "database_dsn_app"
    dsn_file.write_text(migrated_db.app_dsn + "\n", encoding="utf-8")
    master_key_file = tmp_path / "master_key"
    master_key_file.write_text(ROOT_KEY.hex() + "\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_DSN_FILE", str(dsn_file))
    monkeypatch.setenv("MASTER_KEY_FILE", str(master_key_file))
    return migrated_db


@pytest.mark.parametrize(
    "args",
    [
        ["policy", "set", "--execution-slots", "nope"],
        ["policy", "set", "--unknown-option", "1"],
        ["maintenance", "set"],
    ],
)
def test_cli_usage_errors_include_request_id(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert re.search(r"request_id=[0-9a-f-]{36}", result.output)


def test_policy_set_uses_app_dml_and_updates_slots(cli_env):
    engine = cli_env.app_engine()
    try:
        with engine.connect() as conn:
            before = conn.execute(select(instance_state.c.config_revision, instance_state.c.policy_json)).one()

        result = runner.invoke(
            app,
            [
                "policy",
                "set",
                "--video-execution-slots",
                "1",
                "--video-waiting-slots",
                "3",
                "--video-total-timeout-seconds",
                "3600",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "config_revision=2" in result.output
        with engine.connect() as conn:
            after = conn.execute(select(instance_state.c.config_revision, instance_state.c.policy_json)).one()
            slots = conn.execute(
                select(resource_slots.c.slot_no, resource_slots.c.slot_state)
                .where(resource_slots.c.resource_key == "execution:video")
                .order_by(resource_slots.c.slot_no)
            ).all()
        assert before.config_revision == 1
        assert after.config_revision == before.config_revision + 1
        assert after.policy_json["pools"]["video"] == {"execution_slots": 1, "waiting_slots": 3}
        assert after.policy_json["video_total_timeout_seconds"] == 3600
        assert slots == [(1, "active"), (2, "retired")]
    finally:
        engine.dispose()


def test_installed_cli_updates_real_database(cli_env):
    executable = Path(sysconfig.get_path("scripts")) / ("frameread.exe" if os.name == "nt" else "frameread")
    environment = os.environ.copy()
    environment["DATABASE_DSN_FILE"] = str(Path(environment["DATABASE_DSN_FILE"]))

    policy = subprocess.run(  # noqa: S603
        [str(executable), "policy", "set", "--video-execution-slots", "1"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert policy.returncode == 0, policy.stderr

    maintenance = subprocess.run(  # noqa: S603
        [str(executable), "maintenance", "set", "draining"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert maintenance.returncode == 0, maintenance.stderr


def test_policy_growth_reactivates_retired_slots_and_adds_capacity(cli_env):
    assert runner.invoke(app, ["policy", "set", "--execution-slots", "1"]).exit_code == 0
    result = runner.invoke(app, ["policy", "set", "--execution-slots", "3"])
    assert result.exit_code == 0, result.output
    engine = cli_env.app_engine()
    try:
        with engine.connect() as conn:
            slots = conn.execute(
                select(resource_slots.c.slot_no, resource_slots.c.slot_state)
                .where(resource_slots.c.resource_key == "execution:video")
                .order_by(resource_slots.c.slot_no)
            ).all()
            revision = conn.execute(select(instance_state.c.config_revision)).scalar_one()
        assert slots == [(1, "active"), (2, "active"), (3, "active")]
        assert revision == 3
    finally:
        engine.dispose()


def test_policy_set_invalid_value_is_exit_two_and_does_not_write(cli_env):
    engine = cli_env.app_engine()
    try:
        with engine.connect() as conn:
            before = conn.execute(select(instance_state.c.config_revision, instance_state.c.policy_json)).one()

        result = runner.invoke(app, ["policy", "set", "--video-execution-slots", "0"])

        assert result.exit_code == 2, result.output
        assert re.search(r"request_id=[0-9a-f-]{36}", result.output)
        with engine.connect() as conn:
            after = conn.execute(select(instance_state.c.config_revision, instance_state.c.policy_json)).one()
        assert after == before
    finally:
        engine.dispose()


def test_maintenance_set_respects_restore_state_and_reports_request_id(cli_env):
    engine = cli_env.app_engine()
    try:
        result = runner.invoke(app, ["maintenance", "set", "draining"])
        assert result.exit_code == 0, result.output

        with engine.begin() as conn:
            conn.execute(update(instance_state).values(restore_state="review_required"))
        result = runner.invoke(app, ["maintenance", "set", "normal"])
        assert result.exit_code == 1, result.output
        assert re.search(r"request_id=[0-9a-f-]{36}", result.output)

        with engine.connect() as conn:
            row = conn.execute(select(instance_state.c.maintenance_mode, instance_state.c.restore_state)).one()
        assert row == ("draining", "review_required")
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_policy_set_shrinks_without_interrupting_occupied_slot(cli_env):
    async_engine = make_async_engine(cli_env.app_dsn, pool_size=3, pool_timeout=5)
    try:
        first = await submit_admission(
            async_engine,
            AdmissionRequest(key=uuid.uuid4(), request_digest="a" * 64, effective_input={}),
        )
        second = await submit_admission(
            async_engine,
            AdmissionRequest(key=uuid.uuid4(), request_digest="b" * 64, effective_input={}),
        )
        result = runner.invoke(app, ["policy", "set", "--video-execution-slots", "1"])
        assert result.exit_code == 0, result.output

        async with async_engine.connect() as conn:
            occupied_slots = (
                await conn.execute(
                    select(resource_slots.c.slot_no, resource_slots.c.slot_state, resource_slots.c.assigned_task_id)
                    .where(resource_slots.c.resource_key == "execution:video")
                    .order_by(resource_slots.c.slot_no)
                )
            ).all()
        assert occupied_slots == [(1, "active", first.task_id), (2, "retired", second.task_id)]

        third = await submit_admission(
            async_engine,
            AdmissionRequest(key=uuid.uuid4(), request_digest="c" * 64, effective_input={}),
        )

        sync_engine = cli_env.app_engine()
        try:
            with sync_engine.begin() as conn:
                conn.execute(
                    update(resource_slots)
                    .where(resource_slots.c.resource_key == "execution:video")
                    .values(assigned_task_id=None, assigned_fence=None)
                )
        finally:
            sync_engine.dispose()

        fourth = await submit_admission(
            async_engine,
            AdmissionRequest(key=uuid.uuid4(), request_digest="d" * 64, effective_input={}),
        )
    finally:
        await async_engine.dispose()

    engine = cli_env.app_engine()
    try:
        with engine.connect() as conn:
            slots = conn.execute(
                select(resource_slots.c.slot_no, resource_slots.c.slot_state, resource_slots.c.assigned_task_id)
                .where(resource_slots.c.resource_key == "execution:video")
                .order_by(resource_slots.c.slot_no)
            ).all()
            waiting_class = conn.execute(
                select(tasks.c.admission_class).where(tasks.c.id == third.task_id)
            ).scalar_one()
            fourth_class = conn.execute(
                select(tasks.c.admission_class).where(tasks.c.id == fourth.task_id)
            ).scalar_one()
        assert slots[0].slot_state == "active"
        assert slots[1].slot_state == "retired"
        assert slots[1].assigned_task_id is None
        assert slots[0].assigned_task_id == fourth.task_id
        assert {first.task_id, second.task_id} != {slots[0].assigned_task_id, slots[1].assigned_task_id}
        assert waiting_class == "waiting"
        assert fourth_class == "execution"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "maintenance,restore", [("draining", "normal"), ("frozen", "normal"), ("normal", "review_required")]
)
def test_http_maintenance_rejects_new_task_but_replays_and_reads_existing(
    session_app, migrated_db, maintenance, restore
):
    app_instance, password = session_app
    key = str(uuid.uuid4())
    body = {"url": "https://youtu.be/dQw4w9WgXc", "mode": "complete", "depth": "standard"}
    engine = migrated_db.app_engine()
    try:
        with TestClient(app_instance, base_url=ORIGIN) as client:
            csrf = login(client, password).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key}
            accepted = client.post("/api/v1/admin/video-tasks", json=body, headers=headers)
            assert accepted.status_code == 202, accepted.text
            task_id = accepted.json()["task_id"]

            with engine.begin() as conn:
                before = conn.execute(select(tasks.c.id)).all()
                conn.execute(update(instance_state).values(maintenance_mode=maintenance, restore_state=restore))

            replay = client.post("/api/v1/admin/video-tasks", json=body, headers=headers)
            assert replay.status_code == 202, replay.text
            assert replay.json()["task_id"] == task_id and replay.json()["replayed"] is True
            snapshot = client.get(f"/api/v1/admin/tasks/{task_id}")
            assert snapshot.status_code == 200, snapshot.text

            rejected = client.post(
                "/api/v1/admin/video-tasks",
                json=body,
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert rejected.status_code == 503, rejected.text
            assert rejected.json()["error"]["code"] == "MAINTENANCE"

        with engine.connect() as conn:
            after = conn.execute(select(tasks.c.id)).all()
        assert after == before
    finally:
        engine.dispose()
