import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select, update

from frameread.api.admin_app import create_app
from frameread.db.models import admin_sessions, instance_state
from frameread.observability.logging import ALLOWED_FIELDS
from frameread.security.sessions import token_hash

from . import test_admin_health
from .conftest import REDIS_URL_ENV, _required_env

admin_env = test_admin_health.admin_env

pytestmark = pytest.mark.integration
ORIGIN = "http://127.0.0.1:8080"
SESSION = "/api/v1/admin/session"


@pytest.fixture
def session_app(migrated_db, admin_env, tmp_path: Path, monkeypatch):
    admin_env(migrated_db.app_dsn)
    password = secrets.token_urlsafe(24)
    path = tmp_path / "admin_hash"
    path.write_text(PasswordHasher().hash(password) + "\n", encoding="utf-8")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH_FILE", str(path))
    engine = migrated_db.app_engine()
    with engine.connect() as connection:
        epoch = connection.execute(select(instance_state.c.instance_epoch)).scalar_one()
    engine.dispose()
    redis = Redis.from_url(_required_env(REDIS_URL_ENV))
    keys = list(redis.scan_iter(f"fr:{epoch}:login:*"))
    if keys:
        redis.delete(*keys)
    redis.close()
    return create_app(), password


def login(client, password):
    return client.post(SESSION, headers={"Origin": ORIGIN}, json={"password": password})


def test_session_login_read_logout_and_csrf(session_app):
    app, password = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get(SESSION).status_code == 401
        response = login(client, password)
        assert response.status_code == 201, response.text
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/admin" in cookie
        assert "Secure" not in cookie
        body = response.json()
        assert client.get(SESSION).json() == body
        assert client.delete(SESSION, headers={"Origin": ORIGIN}).json()["error"]["code"] == "CSRF_REJECTED"
        old_cookie = client.cookies.get("frameread_admin")
        assert client.delete(SESSION, headers={"Origin": ORIGIN, "X-CSRF-Token": body["csrf_token"]}).status_code == 204
        assert client.get(SESSION, headers={"Cookie": f"frameread_admin={old_cookie}"}).status_code == 401


@pytest.mark.parametrize(
    "headers,method",
    [
        ({}, "post"),
        ({"Origin": "https://127.0.0.1:8080"}, "post"),
        ({"Origin": ORIGIN + "/"}, "post"),
        ({"Origin": "http://attacker.invalid"}, "post"),
        ({"Host": "attacker.invalid"}, "get"),
    ],
)
def test_source_is_checked_before_session_and_payload(session_app, headers, method):
    app, _ = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        response = getattr(client, method)(SESSION, headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ORIGIN_REJECTED"


def test_origin_and_content_type_are_rejected_before_json_parsing(session_app):
    app, _ = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post(SESSION, content="{broken", headers={"Content-Type": "application/json"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ORIGIN_REJECTED"
        response = client.post(SESSION, content="{broken", headers={"Origin": ORIGIN, "Content-Type": "text/plain"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_failure_limit_ignores_forwarded_headers_and_success_does_not_reset(session_app, capsys):
    app, password = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, "wrong").status_code == 401
        assert login(client, password).status_code == 201
        for number in range(4):
            response = client.post(
                SESSION,
                headers={
                    "Origin": ORIGIN,
                    "X-Forwarded-For": f"192.0.2.{number}",
                    "X-Forwarded-Host": "attacker.invalid",
                    "X-Forwarded-Proto": "https",
                },
                json={"password": "wrong"},
            )
            assert response.status_code == 401
        limited = login(client, password)
        assert limited.status_code == 429
        assert 1 <= int(limited.headers["Retry-After"]) <= 900
        assert limited.json()["error"]["retry_after_seconds"] == int(limited.headers["Retry-After"])
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    events = [entry for entry in logs if entry["event"].startswith("login_")]
    assert {entry["event"] for entry in events} == {"login_failed", "login_succeeded", "login_rate_limited"}
    assert all(set(entry) <= ALLOWED_FIELDS for entry in events)
    assert all(password not in json.dumps(entry) and "192.0.2" not in json.dumps(entry) for entry in events)


def test_global_limit_applies_to_new_source(session_app):
    app, password = session_app
    for source in range(6):
        with TestClient(app, base_url=ORIGIN, client=(f"192.0.2.{source}", 4000)) as client:
            for _ in range(5):
                assert login(client, "wrong").status_code == 401
    with TestClient(app, base_url=ORIGIN, client=("192.0.2.100", 4000)) as client:
        assert login(client, password).status_code == 429


def test_token_storage_absolute_expiry_and_last_seen_throttle(session_app, migrated_db):
    app, password = session_app
    engine = migrated_db.app_engine()
    try:
        with TestClient(app, base_url=ORIGIN) as client:
            body = login(client, password).json()
            token = client.cookies.get("frameread_admin")
            with engine.begin() as conn:
                row = conn.execute(select(admin_sessions)).one()
                assert bytes(row.token_hash) == token_hash(token)
                assert bytes(row.csrf_hash) == token_hash(body["csrf_token"])
                assert token.encode() not in bytes(row.token_hash)
                assert (
                    timedelta(hours=11, minutes=59) < row.expires_at - row.created_at < timedelta(hours=12, seconds=1)
                )
                conn.execute(update(admin_sessions).values(last_seen_at=row.created_at - timedelta(hours=3)))
            assert client.get(SESSION).status_code == 200
            with engine.connect() as conn:
                after = conn.execute(select(admin_sessions)).one()
            assert after.version == row.version + 1
            assert client.get(SESSION).status_code == 200
            with engine.begin() as conn:
                assert conn.execute(select(admin_sessions.c.version)).scalar_one() == after.version
                conn.execute(update(admin_sessions).values(expires_at=row.created_at - timedelta(seconds=1)))
            assert client.get(SESSION).status_code == 401
    finally:
        engine.dispose()


def test_frozen_session_reads_do_not_mutate_last_seen(session_app, migrated_db):
    app, password = session_app
    engine = migrated_db.app_engine()
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, password).status_code == 201
        with engine.begin() as conn:
            conn.execute(update(admin_sessions).values(last_seen_at=admin_sessions.c.created_at - timedelta(hours=1)))
            conn.execute(update(instance_state).values(maintenance_mode="frozen"))
            before = conn.execute(select(admin_sessions)).one()
        assert client.get(SESSION).status_code == 200
        assert login(client, "wrong").status_code == 503
        with engine.connect() as conn:
            after = conn.execute(select(admin_sessions)).one()
        assert after == before
    engine.dispose()


@pytest.mark.parametrize(
    "mode,restore,status",
    [
        ("frozen", "normal", 503),
        ("draining", "normal", 201),
        ("normal", "normal", 201),
        ("normal", "review_required", 201),
    ],
)
def test_session_writes_obey_maintenance_gate(session_app, migrated_db, mode, restore, status):
    app, password = session_app
    engine = migrated_db.app_engine()
    with TestClient(app, base_url=ORIGIN) as client:
        csrf = login(client, password).json()["csrf_token"]
        with engine.begin() as conn:
            conn.execute(update(instance_state).values(maintenance_mode=mode, restore_state=restore))
        response = login(client, password)
        assert response.status_code == status
        logout = client.delete(
            SESSION,
            headers={"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"] if status == 201 else csrf},
        )
        assert logout.status_code == (503 if mode == "frozen" else 204)
    engine.dispose()


def test_password_rotation_revokes_old_session_on_restart(session_app, monkeypatch):
    app, password = session_app
    with TestClient(app, base_url=ORIGIN) as client:
        assert login(client, password).status_code == 201
        cookie = client.cookies.get("frameread_admin")
    import os

    Path(os.environ["ADMIN_PASSWORD_HASH_FILE"]).write_text(
        PasswordHasher().hash(secrets.token_urlsafe(24)), encoding="utf-8"
    )
    with TestClient(create_app(), base_url=ORIGIN) as client:
        assert client.get(SESSION, headers={"Cookie": f"frameread_admin={cookie}"}).status_code == 401


def test_five_concurrent_logins_finish_and_queue(session_app, capsys):
    app, password = session_app
    with TestClient(app, base_url=ORIGIN) as client, ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda _: login(client, password), range(5)))
        assert [response.status_code for response in responses] == [201] * 5
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    waits = [entry["queue_wait_ms"] for entry in logs if entry["event"] == "login_succeeded"]
    assert len(waits) == 5 and sum(wait > 10 for wait in waits) >= 3


def test_concurrent_failures_have_bounded_excess(session_app):
    app, _ = session_app
    with TestClient(app, base_url=ORIGIN) as client, ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: login(client, "wrong"), range(10)))
        failures = sum(response.status_code == 401 for response in responses)
        assert 5 <= failures <= 7
        assert all(response.status_code in (401, 429) for response in responses)
        redis = Redis.from_url(_required_env(REDIS_URL_ENV))
        epoch = app.state.runtime.identity.instance_epoch
        assert int(redis.get(f"fr:{epoch}:login:global")) == failures
        redis.close()
