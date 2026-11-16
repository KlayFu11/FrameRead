import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from frameread.db.engine import make_async_engine
from frameread.db.models import instance_state, resource_slots, task_events, task_outbox, tasks
from frameread.domain.errors import AppError, ErrorCode
from frameread.security.crypto import KeyRing
from frameread.services.admission import AdmissionRequest, submit_admission
from frameread.services.task_snapshot import read_snapshot

from . import test_admin_sessions
from .conftest import ROOT_KEY

ORIGIN = test_admin_sessions.ORIGIN
login = test_admin_sessions.login
admin_env = test_admin_sessions.admin_env
session_app = test_admin_sessions.session_app

pytestmark = pytest.mark.integration


def test_admin_can_submit_recover_and_read_queued_task(session_app):
    app, password = session_app
    key = str(uuid.uuid4())
    body = {"url": "https://youtu.be/dQw4w9WgXc", "mode": "complete", "depth": "standard"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert (
            client.post(
                "/api/v1/admin/video-tasks", json=body, headers={"Origin": ORIGIN, "Idempotency-Key": key}
            ).status_code
            == 401
        )
        session = login(client, password).json()
        headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"], "Idempotency-Key": key}
        response = client.post("/api/v1/admin/video-tasks", json=body, headers=headers)
        assert response.status_code == 202, response.text
        accepted = response.json()
        assert set(accepted) == {
            "task_id",
            "kind",
            "status",
            "accepted_at",
            "deadline_at",
            "snapshot_url",
            "replayed",
            "operation_scope",
        }
        assert response.headers["location"] == accepted["snapshot_url"]
        assert accepted["replayed"] is False and accepted["operation_scope"] == "video:new"
        replay = client.post("/api/v1/admin/video-tasks", json=body, headers=headers)
        assert replay.status_code == 202 and replay.json()["task_id"] == accepted["task_id"]
        assert replay.json()["replayed"] is True
        found = client.get(f"/api/v1/admin/operations/video:new/{key}")
        assert found.status_code == 200 and found.json()["task_id"] == accepted["task_id"]
        snapshot = client.get(accepted["snapshot_url"])
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["status"] == "queued" and snapshot.json()["progress"]["stage"] is None
        assert len(snapshot.json()["cursor"].split(".")) == 2
        conflict = client.post("/api/v1/admin/video-tasks", json={**body, "depth": "brief"}, headers=headers)
        assert conflict.status_code == 409 and conflict.json()["error"]["task_id"] == accepted["task_id"]
        assert client.get(f"/api/v1/admin/operations/video:new/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "change,field,code",
    [
        ({"intent": "reinterpret"}, "intent", "intent_not_available"),
        ({"provider_config_id": str(uuid.uuid4())}, "provider_config_id", "config_not_available"),
        ({"asr_config_id": str(uuid.uuid4())}, "asr_config_id", "config_not_available"),
        ({"mode": "topic", "focus": "  "}, "focus", "focus_required"),
        ({"unknown": "value"}, "unknown", "extra_forbidden"),
    ],
)
def test_submission_rejects_unavailable_fields_without_exposing_input(session_app, change, field, code):
    app, password = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        csrf = login(client, password).json()["csrf_token"]
        response = client.post(
            "/api/v1/admin/video-tasks",
            json={
                "url": "https://youtu.be/dQw4w9WgXc",
                **change,
            },
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert response.status_code == 422, response.text
        assert any(item["field"] == field and item["code"] == code for item in response.json()["error"]["details"])
        assert "dQw4w9WgXc" not in response.text


@pytest.mark.asyncio
async def test_concurrent_same_operation_has_one_atomic_acceptance(migrated_db):
    engine = make_async_engine(migrated_db.app_dsn, pool_size=4, pool_timeout=5)
    request = AdmissionRequest(key=uuid.uuid4(), request_digest="a" * 64, effective_input={"url": "example"})
    try:
        first, second = await asyncio.gather(submit_admission(engine, request), submit_admission(engine, request))
        assert first.task_id == second.task_id
        assert {first.replayed, second.replayed} == {False, True}
        snapshot = await read_snapshot(engine, first.task_id, KeyRing(ROOT_KEY, uuid.uuid4()))
        assert snapshot.status == "queued"
        assert snapshot.state_revision == 1 and snapshot.event_seq == 1
        assert snapshot.allowed_actions == ["cancel"]
        assert snapshot.draft_summary is None and snapshot.result is None
        assert snapshot.unknown_call_count == 0
        async with engine.connect() as conn:
            unresolved = (
                await conn.execute(
                    select(
                        tasks.c.source_id,
                        tasks.c.snapshot_id,
                        tasks.c.provider_revision_id,
                        tasks.c.asr_revision_id,
                        tasks.c.result_json,
                        tasks.c.error_json,
                    )
                )
            ).one()
            assert tuple(unresolved) == (None, None, None, None, None, None)
            nullable_references = (
                (
                    await conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' "
                            "AND data_type='uuid' AND is_nullable='YES' "
                            "AND column_name IN ('source_id','snapshot_id','provider_revision_id','asr_revision_id')"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert set(nullable_references) == {"source_id", "snapshot_id", "provider_revision_id", "asr_revision_id"}
            for table in (tasks, task_outbox, task_events):
                assert (await conn.execute(select(func.count()).select_from(table))).scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_capacity_race_full_replay_and_maintenance_recovery(migrated_db):
    engine = make_async_engine(migrated_db.app_dsn, pool_size=4, pool_timeout=5)
    accepted = []
    try:
        # E=2,Q=4。五份已受理，最后一个位置由两个并发请求争用。
        for number in range(5):
            request = AdmissionRequest(key=uuid.uuid4(), request_digest=f"{number:064x}", effective_input={})
            accepted.append((request, await submit_admission(engine, request)))
        outcomes = await asyncio.gather(
            *(
                submit_admission(
                    engine, AdmissionRequest(key=uuid.uuid4(), request_digest="f" * 64, effective_input={})
                )
                for _ in range(2)
            ),
            return_exceptions=True,
        )
        assert sum(not isinstance(item, Exception) for item in outcomes) == 1
        assert [item.code for item in outcomes if isinstance(item, AppError)] == [ErrorCode.QUEUE_FULL]
        async with engine.begin() as conn:
            for table in (tasks, task_outbox, task_events):
                assert (await conn.execute(select(func.count()).select_from(table))).scalar_one() == 6
            assert (
                await conn.execute(
                    select(func.count())
                    .select_from(resource_slots)
                    .where(resource_slots.c.assigned_task_id.is_not(None))
                )
            ).scalar_one() == 2
            statuses = (await conn.execute(select(task_outbox.c.delivery_status))).scalars().all()
            assert statuses.count("pending") == 2 and statuses.count("blocked") == 4
            await conn.execute(update(instance_state).values(maintenance_mode="frozen"))
        replay = await submit_admission(engine, accepted[0][0])
        assert replay.task_id == accepted[0][1].task_id and replay.replayed
        with pytest.raises(AppError) as conflict:
            await submit_admission(
                engine,
                AdmissionRequest(
                    key=accepted[0][0].key,
                    request_digest="e" * 64,
                    effective_input={},
                ),
            )
        assert conflict.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
        with pytest.raises(AppError) as maintenance:
            await submit_admission(
                engine, AdmissionRequest(key=uuid.uuid4(), request_digest="b" * 64, effective_input={})
            )
        assert maintenance.value.code == ErrorCode.MAINTENANCE
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admission_failure_rolls_back_task_outbox_event_and_slot(migrated_db):
    # 真实 PG 约束触发事务失败，证明已写 task 不会遗留。
    migration = migrated_db.migrate_engine()
    with migration.begin() as conn:
        conn.execute(text("ALTER TABLE task_events ADD CONSTRAINT reject_acceptance CHECK (event_type <> 'accepted')"))
    migration.dispose()
    engine = make_async_engine(migrated_db.app_dsn, pool_size=4, pool_timeout=5)
    try:
        with pytest.raises(AppError) as error:
            await submit_admission(
                engine, AdmissionRequest(key=uuid.uuid4(), request_digest="a" * 64, effective_input={})
            )
        assert error.value.code == ErrorCode.DEPENDENCY_UNAVAILABLE
        async with engine.connect() as conn:
            for table in (tasks, task_outbox, task_events):
                assert (await conn.execute(select(func.count()).select_from(table))).scalar_one() == 0
            assert (
                await conn.execute(
                    select(func.count())
                    .select_from(resource_slots)
                    .where(resource_slots.c.assigned_task_id.is_not(None))
                )
            ).scalar_one() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "maintenance,restore,expected",
    [
        ("normal", "normal", ["cancel"]),
        ("draining", "normal", ["cancel"]),
        ("frozen", "normal", []),
        ("normal", "review_required", []),
    ],
)
async def test_snapshot_actions_follow_current_instance_gate(migrated_db, maintenance, restore, expected):
    engine = make_async_engine(migrated_db.app_dsn, pool_size=4, pool_timeout=5)
    try:
        accepted = await submit_admission(
            engine, AdmissionRequest(key=uuid.uuid4(), request_digest="a" * 64, effective_input={})
        )
        async with engine.begin() as conn:
            installation_id = (await conn.execute(select(instance_state.c.installation_id))).scalar_one()
            await conn.execute(update(instance_state).values(maintenance_mode=maintenance, restore_state=restore))
        snapshot = await read_snapshot(engine, accepted.task_id, KeyRing(ROOT_KEY, installation_id))
        assert snapshot.status == "queued"
        assert snapshot.allowed_actions == expected
    finally:
        await engine.dispose()
