import json
import sys
from pathlib import Path

# 断言各运行服务满足 S0 加固约束（Q13、SPEC §19），且 api-admin 就绪分项全部 ready


def check_service(name: str, info: dict) -> list[str]:
    cfg, host = info["Config"], info["HostConfig"]
    problems = []
    user = cfg.get("User") or ""
    if user in ("", "0", "root") or user.startswith(("0:", "root:")):
        problems.append("以 root 运行")
    if not host.get("ReadonlyRootfs"):
        problems.append("根文件系统可写")
    if host.get("Memory", 0) <= 0:
        problems.append("缺少内存限制")
    if host.get("NanoCpus", 0) <= 0:
        problems.append("缺少 CPU 限制")
    if (host.get("PidsLimit") or 0) <= 0:
        problems.append("缺少 pids 限制")
    if host.get("Privileged"):
        problems.append("privileged")
    mounts = [m.get("Source", "") for m in info.get("Mounts", [])]
    if any(src.endswith("docker.sock") for src in mounts):
        problems.append("挂载了 Docker socket")
    state = info["State"]
    health = state.get("Health", {}).get("Status")
    if not state.get("Running") or health not in (None, "healthy"):
        problems.append(f"状态异常 running={state.get('Running')} health={health}")
    return [f"{name}: {p}" for p in problems]


def main() -> int:
    workdir = Path(sys.argv[1])
    problems = []
    for name in sys.argv[2:]:
        (info,) = json.loads((workdir / f"{name}.json").read_text(encoding="utf-8"))
        problems += check_service(name, info)
    # ready.json 由 probe_ready.sh 输出：{live, ready, status, checks: {name: [status, detail]}}
    ready = json.loads((workdir / "ready.json").read_text(encoding="utf-8"))
    checks = {name: value[0] for name, value in ready["checks"].items()}
    expected = {"postgres", "migration_head", "root_key", "redis"}
    if ready["live"] != 200 or ready["ready"] != 200 or ready["status"] != "ready" or set(checks) != expected:
        problems.append(f"api-admin ready 异常: {ready}")
    elif any(status != "ready" for status in checks.values()):
        problems.append(f"api-admin 分项未就绪: {checks}")
    for p in problems:
        print(p, file=sys.stderr)
    print("OK" if not problems else f"{len(problems)} 项不符合")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
