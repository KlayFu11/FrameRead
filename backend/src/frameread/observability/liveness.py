import argparse
import os
import sys
import time
from pathlib import Path

# Worker 与 control 没有 HTTP 端口：主循环定期写 tmpfs 心跳文件，live 由 CLI 检查其修改时间（D13）。
# 本模块只用标准库，作为容器健康检查入口时启动足够快，不受 Compose 3s 超时影响。

HEARTBEAT_DIR_ENV = "FRAMEREAD_HEARTBEAT_DIR"
DEFAULT_HEARTBEAT_DIR = "/run/frameread"


def heartbeat_path(directory: Path, name: str) -> Path:
    return directory / f"{name}.alive"


def touch_heartbeat(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    heartbeat_path(directory, name).touch()


def is_live(directory: Path, name: str, max_age_seconds: float) -> bool:
    try:
        mtime = heartbeat_path(directory, name).stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - mtime <= max_age_seconds


def main(argv: list[str] | None = None, *, prog: str = "frameread-live") -> int:
    parser = argparse.ArgumentParser(prog=prog, description="检查 worker/control 心跳文件")
    parser.add_argument("--name", required=True, choices=["worker", "control"])
    parser.add_argument("--max-age", type=float, default=30.0)
    args = parser.parse_args(argv)
    directory = Path(os.environ.get(HEARTBEAT_DIR_ENV, DEFAULT_HEARTBEAT_DIR))
    return 0 if is_live(directory, args.name, args.max_age) else 1


if __name__ == "__main__":
    sys.exit(main())
