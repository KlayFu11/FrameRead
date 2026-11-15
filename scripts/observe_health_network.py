import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

# 在同时连接 internal 与 edge 网络的独立验收容器中运行，观察实际健康请求期间的接口发送计数。


def default_route() -> tuple[str, str]:
    for line in Path("/proc/net/route").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == "00000000":
            gateway = socket.inet_ntoa(struct.pack("<I", int(fields[2], 16)))
            return fields[0], gateway
    raise RuntimeError("验收容器必须有独立的 edge 默认路由")


def sent(interface: str) -> tuple[int, int]:
    root = Path("/sys/class/net") / interface / "statistics"
    return int((root / "tx_packets").read_text()), int((root / "tx_bytes").read_text())


def get_health(name: str) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:8000/health/{name}", timeout=3
    ) as response:
        assert response.status == 200
        return str(json.load(response)["status"])


def main() -> None:
    interface, gateway = default_route()
    assert interface != "lo"
    assert get_health("ready") == "ready"
    before = sent(interface)
    started = time.monotonic()
    cli_seconds = []
    with tempfile.TemporaryDirectory() as heartbeat_dir:
        env = dict(os.environ, FRAMEREAD_HEARTBEAT_DIR=heartbeat_dir)
        for name in ("worker", "control"):
            (Path(heartbeat_dir) / f"{name}.alive").touch()
        for _ in range(12):
            assert get_health("live") == "live"
            assert get_health("ready") == "ready"
            for name in ("worker", "control"):
                cli_started = time.monotonic()
                result = subprocess.run(
                    ["/app/.venv/bin/frameread", "health", "live", "--name", name],
                    env=env,
                    timeout=3,
                    check=False,
                )
                assert result.returncode == 0
                cli_seconds.append(time.monotonic() - cli_started)
            # 覆盖至少两个 5s 探针缓存周期，验证真正执行探针的请求。
            time.sleep(1)
    after = sent(interface)
    assert after == before, (before, after)
    # 只向本地 Docker 网关发送独立测试包，证明本接口计数器可观察到发送行为。
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        control.sendto(b"frameread-counter-control", (gateway, 9))
    control_after = sent(interface)
    assert control_after[0] > after[0], (after, control_after)
    print(
        json.dumps(
            {
                "method": "Linux interface TX counters (not packet capture)",
                "interface": interface,
                "requests": {"live": 12, "ready": 12},
                "installed_cli_calls": len(cli_seconds),
                "installed_cli_max_seconds": round(max(cli_seconds), 3),
                "observation_seconds": round(time.monotonic() - started, 2),
                "health_tx_packets": after[0] - before[0],
                "health_tx_bytes": after[1] - before[1],
                "positive_control_tx_packets": control_after[0] - after[0],
            }
        )
    )


if __name__ == "__main__":
    main()
