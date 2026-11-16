# 目的：在隔离的 S0 Compose 项目中验证真实 HTTP、依赖故障与来源转发；临时凭据仅写入 ignored tmp。
import argparse
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "tmp" / "s0-admin"
CLI = ROOT / "backend" / ".venv" / ("Scripts/frameread.exe" if os.name == "nt" else "bin/frameread")
PROJECT = "frameread-s0-t02"
ORIGIN = "http://127.0.0.1:8080"
SESSION = "/api/v1/admin/session"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", str(ROOT / "deploy/compose.yaml")]
counter = 0


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True, **kwargs)  # noqa: S603


def compose(*args):
    return run([*COMPOSE, *args])


def request(path=SESSION, method="GET", payload=None, headers=None, cookie="cookies"):
    global counter
    counter += 1
    body = WORK / f"response-{counter}.json"
    head = WORK / f"headers-{counter}.txt"
    jar = WORK / cookie
    command = [
        "curl.exe" if os.name == "nt" else "curl",
        "--silent",
        "--show-error",
        "--max-time",
        "15",
        "--output",
        str(body),
        "--dump-header",
        str(head),
        "--write-out",
        "%{http_code}",
        "--cookie",
        str(jar),
        "--cookie-jar",
        str(jar),
        "--request",
        method,
        ORIGIN + path,
    ]
    if payload is not None:
        data = WORK / f"request-{counter}.json"
        data.write_text(json.dumps(payload), encoding="utf-8")
        command.extend(["--data-binary", "@" + str(data), "--header", "Content-Type: application/json"])
    for key, value in (headers or {}).items():
        command.extend(["--header", f"{key}: {value}"])
    status = int(run(command).stdout)
    return status, json.loads(body.read_text(encoding="utf-8")) if body.stat().st_size else None


def prepare():
    WORK.mkdir(parents=True, exist_ok=True)
    secret_dir = ROOT / "deploy/secrets"
    if not secret_dir.exists():
        run([str(CLI), "secrets", "init", "--dir", str(secret_dir)])
    if (secret_dir / "admin_password_hash").exists():
        raise RuntimeError("Refusing to replace an existing acceptance password")
    password = secrets.token_urlsafe(32)
    (WORK / "password").write_text(password, encoding="utf-8")
    run(
        [str(CLI), "admin", "set-password", "--out", str(secret_dir / "admin_password_hash")],
        input=password + "\n" + password + "\n",
    )
    print("Prepared isolated secrets and temporary acceptance password")


def http_acceptance():
    password = (WORK / "password").read_text(encoding="utf-8")
    (WORK / "cookies").unlink(missing_ok=True)
    assert request()[0] == 401
    assert request(method="POST", payload={"password": password})[0] == 403
    assert (
        request(method="POST", payload={"password": password}, headers={"Origin": "https://127.0.0.1:8080"})[0] == 403
    )
    assert request(headers={"Host": "attacker.invalid"})[0] == 403
    status, session = request(method="POST", payload={"password": password}, headers={"Origin": ORIGIN})
    assert status == 201
    assert request()[0] == 200
    assert request(method="DELETE", headers={"Origin": ORIGIN})[0] == 403
    for path in ("/docs", "/redoc", "/openapi.json", "/health/live", "/health/ready", "/api/v1/public/session"):
        assert request(path=path)[0] == 404
    compose("stop", "redis")
    try:
        assert request(method="POST", payload={"password": password}, headers={"Origin": ORIGIN})[0] == 503
        assert request()[0] == 200
    finally:
        compose("start", "--wait", "redis")
    compose("stop", "postgres")
    try:
        status, body = request()
        assert status == 503 and body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    finally:
        compose("start", "--wait", "postgres")
    assert request()[0] == 200
    shutil.copyfile(WORK / "cookies", WORK / "old-cookies")
    assert request(method="DELETE", headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]})[0] == 204
    assert request(cookie="old-cookies")[0] == 401
    for index in range(5):
        assert (
            request(
                method="POST",
                payload={"password": "incorrect-test-password"},
                headers={"Origin": ORIGIN, "X-Forwarded-For": f"192.0.2.{index}"},
            )[0]
            == 401
        )
    status, body = request(method="POST", payload={"password": password}, headers={"Origin": ORIGIN})
    assert status == 429 and body["error"]["retry_after_seconds"] > 0
    print(
        json.dumps(
            {
                "http_requests": counter,
                "lifecycle": "passed",
                "redis_outage": "passed",
                "postgres_outage": "passed",
                "spoofed_forwarding_rate_limit": "passed",
            }
        )
    )


def reset_limits():
    code = """
from frameread.settings import load_secrets, AdminSecrets
from redis import Redis
from sqlalchemy import select
from frameread.db.engine import make_engine
from frameread.db.models import instance_state
secrets = load_secrets(AdminSecrets)
engine = make_engine(secrets.secret('database_dsn_file'), pool_size=1, pool_timeout=5)
with engine.connect() as conn:
    epoch = conn.execute(select(instance_state.c.instance_epoch)).scalar_one()
redis = Redis.from_url(secrets.secret('redis_url_file'))
keys = list(redis.scan_iter(f'fr:{epoch}:login:*'))
if keys:
    redis.delete(*keys)
redis.close()
engine.dispose()
"""
    compose("exec", "-T", "api-admin", "python", "-c", code)


def process_acceptance():
    reset_limits()
    password = (WORK / "password").read_text(encoding="utf-8")
    assert request(method="POST", payload={"password": password}, headers={"Origin": ORIGIN})[0] == 201
    shutil.copyfile(WORK / "cookies", WORK / "rotation-cookie")
    replacement = secrets.token_urlsafe(32)
    run(
        [str(CLI), "admin", "set-password", "--force", "--out", str(ROOT / "deploy/secrets/admin_password_hash")],
        input=replacement + "\n" + replacement + "\n",
    )
    (WORK / "password").write_text(replacement, encoding="utf-8")
    compose("up", "-d", "--force-recreate", "--wait", "api-admin")
    compose("restart", "gateway")
    assert request(cookie="rotation-cookie")[0] == 401
    assert request(method="POST", payload={"password": replacement}, headers={"Origin": ORIGIN})[0] == 201
    seed = """
import secrets
from datetime import timedelta
from sqlalchemy import insert, select, delete
from frameread.settings import load_secrets, ServiceSecrets
from frameread.db.engine import make_engine
from frameread.db.models import admin_sessions
from frameread.db.uow import UnitOfWork
engine = make_engine(load_secrets(ServiceSecrets).secret('database_dsn_file'), pool_size=1, pool_timeout=5)
with UnitOfWork(engine) as uow:
    now = uow.db_now()
    for age in (2, 3, 0.5, -1):
        uow.execute(insert(admin_sessions).values(token_hash=secrets.token_bytes(32), csrf_hash=secrets.token_bytes(32),
            credential_generation='0123456789abcdef', expires_at=now-timedelta(days=age), last_seen_at=now,
            deleted_at=now if age == 3 else None))
    uow.commit()
engine.dispose()
"""
    compose("exec", "-T", "api-admin", "python", "-c", seed)
    compose("exec", "-T", "control", "frameread", "control", "cleanup-sessions")
    verify = """
from sqlalchemy import select, func
from frameread.settings import load_secrets, ServiceSecrets
from frameread.db.engine import make_engine
from frameread.db.models import admin_sessions
engine = make_engine(load_secrets(ServiceSecrets).secret('database_dsn_file'), pool_size=1, pool_timeout=5)
with engine.connect() as conn:
    assert conn.execute(select(func.count()).select_from(admin_sessions).where(
        admin_sessions.c.credential_generation == '0123456789abcdef')).scalar_one() == 2
engine.dispose()
"""
    compose("exec", "-T", "api-admin", "python", "-c", verify)
    for invalid in ("/run/secrets/missing-admin-hash", "/dev/null"):
        result = subprocess.run(  # noqa: S603
            [*COMPOSE, "run", "--rm", "--no-deps", "-e", "ADMIN_PASSWORD_HASH_FILE=" + invalid, "api-admin"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
    print(
        json.dumps(
            {
                "rotation_old_cookie": "401",
                "new_password": "201",
                "control_cleanup_retained": 2,
                "missing_hash_process": "nonzero",
                "empty_hash_process": "nonzero",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "http", "process", "reset-limits"])
    args = parser.parse_args()
    {"prepare": prepare, "http": http_acceptance, "process": process_acceptance, "reset-limits": reset_limits}[
        args.phase
    ]()
