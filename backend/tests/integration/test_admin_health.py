import os
import secrets
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi import Depends
from fastapi.testclient import TestClient

from frameread.api.admin_app import create_app
from frameread.api.runtime import AdminRuntime, require_runtime
from frameread.db.bootstrap import FatalStartupError

from .conftest import REDIS_URL_ENV, ROOT_KEY, _required_env

pytestmark = pytest.mark.integration

SETTINGS = """
[admin]
origins = ["http://127.0.0.1:8080"]

[policy.pools.video]
execution_slots = 2
waiting_slots = 4
"""


@pytest.fixture
def admin_env(tmp_path: Path, monkeypatch):
    def configure(dsn: str, *, redis_url: str | None = None, root_key: bytes = ROOT_KEY) -> None:
        files = {
            "DATABASE_DSN_FILE": dsn,
            "REDIS_URL_FILE": redis_url or _required_env(REDIS_URL_ENV),
            "MASTER_KEY_FILE": root_key.hex(),
            "ADMIN_PASSWORD_HASH_FILE": PasswordHasher().hash(secrets.token_urlsafe(24)),
        }
        for env, value in files.items():
            path = tmp_path / env.lower()
            path.write_text(value + "\n", encoding="utf-8")
            monkeypatch.setenv(env, str(path))
        settings = tmp_path / "settings.toml"
        settings.write_text(SETTINGS, encoding="utf-8")
        monkeypatch.setenv("FRAMEREAD_SETTINGS", str(settings))

    return configure


def ready(client: TestClient):
    resp = client.get("/health/ready")
    return resp.status_code, resp.json()["status"], {c["name"]: c for c in resp.json()["checks"]}


def test_ready_when_all_dependencies_ok(migrated_db, admin_env):
    admin_env(migrated_db.app_dsn)
    with TestClient(create_app()) as client:
        assert client.get("/health/live").json() == {"status": "live"}
        code, status, checks = ready(client)
    assert (code, status) == (200, "ready")
    assert {n: c["status"] for n, c in checks.items()} == {
        "postgres": "ready",
        "migration_head": "ready",
        "root_key": "ready",
        "redis": "ready",
    }


def test_redis_down_is_degraded_but_200(migrated_db, admin_env, closing_port):
    admin_env(migrated_db.app_dsn, redis_url=f"redis://127.0.0.1:{closing_port}/0")
    with TestClient(create_app()) as client:
        code, status, checks = ready(client)
    assert (code, status) == (200, "degraded")
    assert checks["redis"]["status"] == "degraded" and checks["redis"]["detail"] == "connection_failed"


def test_postgres_unreachable_is_unavailable_and_writes_refused(admin_env, closing_port):
    admin_env(f"postgresql+psycopg://frameread_app:x@127.0.0.1:{closing_port}/none")
    app = create_app()

    @app.post("/probe-write")
    async def probe_write(_: AdminRuntime = Depends(require_runtime)) -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as client:
        code, status, checks = ready(client)
        write = client.post("/probe-write")
    assert (code, status) == (503, "unavailable")
    assert checks["postgres"]["status"] == "unavailable"
    assert write.status_code == 503 and write.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_unmigrated_database_reports_not_ready(fresh_db, admin_env):
    admin_env(fresh_db.app_dsn)
    with TestClient(create_app()) as client:
        code, status, checks = ready(client)
    assert (code, status) == (503, "unavailable")
    assert checks["migration_head"]["detail"] == "head_mismatch"
    assert checks["root_key"]["detail"] == "not_verified"


def test_wrong_root_key_fails_startup(migrated_db, admin_env):
    admin_env(migrated_db.app_dsn, root_key=bytes(32))
    with pytest.raises(FatalStartupError), TestClient(create_app()):
        pass


@pytest.mark.parametrize("missing", ["MASTER_KEY_FILE", "DATABASE_DSN_FILE", "ADMIN_PASSWORD_HASH_FILE"])
def test_missing_secret_env_fails_before_serving(fresh_db, admin_env, monkeypatch, missing):
    admin_env(fresh_db.app_dsn)
    monkeypatch.delenv(missing)
    with pytest.raises(Exception, match=missing):
        create_app()


def test_empty_master_key_file_fails(fresh_db, admin_env):
    admin_env(fresh_db.app_dsn)
    Path(os.environ["MASTER_KEY_FILE"]).write_text("\n", encoding="utf-8")
    with pytest.raises(Exception, match="MASTER_KEY_FILE"), TestClient(create_app()):
        pass
