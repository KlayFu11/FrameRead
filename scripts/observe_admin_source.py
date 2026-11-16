# 目的：只读核验真实 Compose 登录来源、伪造 XFF 的计数归属与日志字段；不输出凭据或派生密钥。
import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_LOG_FIELDS = {"event", "request_id", "status", "duration_seconds"}


def inside(candidates: list[str], expected_failures: int) -> dict:
    from redis import Redis

    from frameread.db.bootstrap import parse_root_key, verify_startup
    from frameread.db.engine import make_engine
    from frameread.observability.logging import ALLOWED_FIELDS
    from frameread.security.crypto import KeyPurpose
    from frameread.security.sessions import source_hash
    from frameread.settings import ServiceSecrets, load_secrets

    secrets = load_secrets(ServiceSecrets)
    engine = make_engine(secrets.secret("database_dsn_file"), pool_size=1, pool_timeout=5)
    try:
        with engine.connect() as connection:
            identity = verify_startup(connection, parse_root_key(secrets.secret("master_key_file")))
    finally:
        engine.dispose()
    key = identity.keyring.derive(KeyPurpose.SESSION_CSRF)
    prefix = f"fr:{identity.instance_epoch}:login:"
    with Redis.from_url(secrets.secret("redis_url_file"), decode_responses=True) as redis:
        source_keys = set(redis.scan_iter(match=prefix + "*")) - {prefix + "global"}
        assert len(source_keys) == 1, "Expected one shared source counter after spoofed-XFF requests"
        matching = [address for address in candidates if prefix + source_hash(key, address) in source_keys]
        assert len(matching) == 1, "Actual source did not uniquely match the observed network candidates"
        observed_key = next(iter(source_keys))
        source_count = int(redis.get(observed_key))
        global_count = int(redis.get(prefix + "global"))
        assert source_count == global_count == expected_failures, "Unexpected failure counter values"
        spoofed_keys = [prefix + source_hash(key, f"192.0.2.{index}") for index in range(expected_failures)]
        assert not any(redis.exists(candidate) for candidate in spoofed_keys), "Spoofed XFF changed source keys"
    return {
        "method": "Read-only Redis HMAC source-key comparison against Docker network and Desktop candidates",
        "observed_source": matching[0],
        "source_counter": source_count,
        "global_counter": global_count,
        "source_key_count": len(source_keys),
        "spoofed_source_keys": 0,
        "log_allowlist": sorted(ALLOWED_FIELDS | {"stack"}),
    }


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    # 命令仅由本脚本的固定 Compose/inspect 参数构造，不启用 shell。
    result = subprocess.run(  # noqa: S603
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False, **kwargs
    )
    if result.returncode:
        # Docker 参数与数据库异常可能包含敏感值，只保留异常类型和源码位置。
        diagnostic = [line for line in result.stderr.splitlines() if line.lstrip().startswith("File ")]
        last_line = result.stderr.splitlines()[-1] if result.stderr else "CommandFailed"
        error_type = last_line.partition(":")[0]
        raise RuntimeError(f"Observer command failed: {error_type}; frames={diagnostic}")
    return result


def audit_logs(compose: list[str], allowed_fields: set[str]) -> dict:
    counts = {}
    login_events = set()
    for service, fields in (("api-admin", allowed_fields), ("gateway", GATEWAY_LOG_FIELDS)):
        result = run([*compose, "logs", "--no-color", "--no-log-prefix", service])
        records = []
        for line in (result.stdout + result.stderr).splitlines():
            if not line.startswith("{"):
                continue
            record = json.loads(line)
            assert set(record) <= fields, f"Unexpected {service} log fields"
            assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line), "Plaintext IP in JSON log"
            records.append(record)
            if service == "api-admin" and str(record.get("event", "")).startswith("login_"):
                login_events.add(record["event"])
        assert records, f"No structured log records found for {service}"
        counts[service] = len(records)
    assert {"login_succeeded", "login_failed", "login_rate_limited"} <= login_events
    return {"json_records_checked": counts, "login_events": sorted(login_events), "allowlist": "passed"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--project", default="frameread-s0-t02")
    parser.add_argument("--candidates", default="[]")
    parser.add_argument("--expected-failures", type=int, default=5)
    args = parser.parse_args()
    if args.inside:
        print(json.dumps(inside(json.loads(args.candidates), args.expected_failures)))
        return
    compose = ["docker", "compose", "-p", args.project, "-f", str(ROOT / "deploy/compose.yaml")]
    gateway_id = run([*compose, "ps", "-q", "gateway"]).stdout.strip()
    assert gateway_id, "Gateway is not running"
    gateway = json.loads(run(["docker", "inspect", gateway_id]).stdout)[0]
    candidates = {"127.0.0.1", "::1"}
    candidates.update(str(address) for address in ipaddress.ip_network("192.168.65.0/24").hosts())
    for network in gateway["NetworkSettings"]["Networks"].values():
        candidates.update(value for field in ("Gateway", "IPAddress", "IPv6Gateway") if (value := network[field]))
    result = run(
        [
            *compose,
            "exec",
            "-T",
            "api-admin",
            "python",
            "-",
            "--inside",
            "--candidates",
            json.dumps(sorted(candidates)),
            "--expected-failures",
            str(args.expected_failures),
        ],
        input=Path(__file__).read_text(encoding="utf-8"),
    )
    observation = json.loads(result.stdout)
    fields = set(observation.pop("log_allowlist"))
    observation["logs"] = audit_logs(compose, fields)
    print(json.dumps(observation))


if __name__ == "__main__":
    main()
