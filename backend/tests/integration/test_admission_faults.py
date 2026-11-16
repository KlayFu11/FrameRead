import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from frameread.api.admin_app import create_app
from frameread.db.models import task_events, task_outbox, tasks

from ..faults.pg_wire_proxy import (
    DROP_BEFORE_TASK_INSERT,
    DROP_COMMIT,
    FORWARD_COMMIT_DROP_RESPONSE,
    PostgreSQLWireProxy,
    running_pg_wire_proxy,
)
from . import test_admin_health, test_admin_sessions
from .conftest import REDIS_URL_ENV, _required_env

pytestmark = [pytest.mark.integration, pytest.mark.faults]

ORIGIN = test_admin_sessions.ORIGIN
admin_env = test_admin_health.admin_env
BODY = {"url": "https://youtu.be/dQw4w9WgXc", "mode": "complete", "depth": "standard"}


def _proxy_dsn(dsn: str, proxy: PostgreSQLWireProxy) -> str:
    url = make_url(dsn).set(host="127.0.0.1", port=proxy.port)
    return url.update_query_dict({"sslmode": "disable"}).render_as_string(hide_password=False)


@contextmanager
def _fault_client(migrated_db, admin_env, mode):
    source = make_url(migrated_db.app_dsn)
    assert source.host is not None and source.port is not None
    with running_pg_wire_proxy(source.host, source.port, mode=mode) as proxy:
        admin_env(_proxy_dsn(migrated_db.app_dsn, proxy))
        password = "ticket-05-test-password"
        Path(os.environ["ADMIN_PASSWORD_HASH_FILE"]).write_text(
            PasswordHasher().hash(password) + "\n", encoding="utf-8"
        )
        app = create_app()
        with TestClient(app, base_url=ORIGIN) as client:
            assert app.state.runtime.identity is not None
            redis = Redis.from_url(_required_env(REDIS_URL_ENV))
            keys = list(redis.scan_iter(f"fr:{app.state.runtime.identity.instance_epoch}:login:*"))
            if keys:
                redis.delete(*keys)
            redis.close()
            csrf = client.post("/api/v1/admin/session", headers={"Origin": ORIGIN}, json={"password": password}).json()[
                "csrf_token"
            ]
            yield client, proxy, csrf


def _submit(client: TestClient, csrf: str, key: str):
    return client.post(
        "/api/v1/admin/video-tasks",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key},
        json=BODY,
    )


def _counts(db) -> tuple[int, int, int]:
    engine = db.app_engine()
    try:
        with engine.connect() as conn:
            return tuple(
                conn.execute(select(text("count(*)")).select_from(table)).scalar_one()
                for table in (tasks, task_outbox, task_events)
            )
    finally:
        engine.dispose()


def test_drop_commit_returns_admission_unconfirmed_and_same_key_can_retry(migrated_db, admin_env, capsys):
    key = str(uuid.uuid4())
    with _fault_client(migrated_db, admin_env, DROP_COMMIT) as (client, proxy, csrf):
        before = proxy.commit_commands
        proxy.arm()
        uncertain = _submit(client, csrf, key)
        assert uncertain.status_code == 503, uncertain.text
        assert uncertain.json()["error"]["code"] == "ADMISSION_UNCONFIRMED"
        assert uncertain.json()["error"]["action"] == "resolve_same_key"
        assert proxy.commit_commands == before + 2
        assert _counts(migrated_db) == (0, 0, 0)

        recovered = _submit(client, csrf, key)
        assert recovered.status_code == 202, recovered.text
        assert recovered.json()["replayed"] is False
        assert _counts(migrated_db) == (1, 1, 1)
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert sum(entry.get("commit_outcome") == "unknown" for entry in logs) == 1


def test_forwarded_commit_with_lost_response_replays_original_task(migrated_db, admin_env, capsys):
    key = str(uuid.uuid4())
    with _fault_client(migrated_db, admin_env, FORWARD_COMMIT_DROP_RESPONSE) as (client, proxy, csrf):
        before = proxy.commit_commands
        proxy.arm()
        recovered = _submit(client, csrf, key)
        assert recovered.status_code == 202, recovered.text
        body = recovered.json()
        assert body["replayed"] is True
        assert body["task_id"]
        assert proxy.commit_commands == before + 2
        assert _counts(migrated_db) == (1, 1, 1)
        lookup = client.get(f"/api/v1/admin/operations/video:new/{key}")
        assert lookup.status_code == 200 and lookup.json()["task_id"] == body["task_id"]
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert sum(entry.get("commit_outcome") == "unknown" for entry in logs) == 1


def test_disconnect_before_task_insert_rolls_back_without_residue(migrated_db, admin_env, capsys):
    key = str(uuid.uuid4())
    with _fault_client(migrated_db, admin_env, DROP_BEFORE_TASK_INSERT) as (client, proxy, csrf):
        before = proxy.commit_commands
        proxy.arm()
        failed = _submit(client, csrf, key)
        assert failed.status_code == 503, failed.text
        assert failed.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert proxy.commit_commands == before + 1
        assert _counts(migrated_db) == (0, 0, 0)
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert any(entry.get("commit_outcome") == "rolled_back" for entry in logs)


def test_serializable_failure_retries_whole_transaction_and_keeps_identity(migrated_db):
    migration = migrated_db.migrate_engine()
    with migration.begin() as conn:
        conn.execute(text("CREATE TABLE ticket05_serializable_probe (id int PRIMARY KEY, value int NOT NULL)"))
        conn.execute(text("INSERT INTO ticket05_serializable_probe VALUES (1, 0)"))
        conn.execute(text("GRANT SELECT, UPDATE ON ticket05_serializable_probe TO frameread_app"))
    migration.dispose()

    from frameread.db.engine import make_engine
    from frameread.db.uow import run_transaction

    engine = make_engine(migrated_db.app_dsn, pool_size=4, pool_timeout=5)
    barrier = threading.Barrier(2, timeout=10)
    attempts: dict[str, int] = {"left": 0, "right": 0}
    identities: list[uuid.UUID] = []
    identity = uuid.uuid4()
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        def transaction(uow):
            attempts[name] += 1
            identities.append(identity)
            uow.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            uow.execute(text("SELECT value FROM ticket05_serializable_probe WHERE id = 1")).scalar_one()
            if attempts[name] == 1:
                barrier.wait()
            uow.execute(text("UPDATE ticket05_serializable_probe SET value = value + 1 WHERE id = 1"))

        try:
            run_transaction(engine, transaction)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    try:
        assert errors == []
        assert sorted(attempts.values()) == [1, 2]
        assert identities and set(identities) == {identity}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT value FROM ticket05_serializable_probe WHERE id = 1")).scalar_one() == 2
    finally:
        engine.dispose()
