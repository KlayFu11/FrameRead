import argparse
import http.client
import ipaddress
import json
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

# 通过真实 API 地址变化验证 gateway 自动恢复；只用于独立 S0 验收项目，最后恢复原网络地址。


def docker(*arguments: str) -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker CLI is required")
    result = subprocess.run(  # noqa: S603 - 固定 Docker 可执行文件与 argv，不经过 shell。
        [executable, *arguments], capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode:
        raise RuntimeError(f"Docker operation failed: {arguments[0]}")
    return result.stdout.strip()


def inspect(kind: str, name: str) -> dict:
    return json.loads(docker(kind, "inspect", name))[0]


def session_status(origin: str) -> int:
    address = urlsplit(origin)
    if address.scheme != "http" or address.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("The acceptance origin must be a loopback HTTP endpoint")
    if address.username or address.password or address.path not in ("", "/") or address.query or address.fragment:
        raise ValueError("The acceptance origin must not contain credentials or a path")
    connection = http.client.HTTPConnection(address.hostname, address.port or 80, timeout=2)
    try:
        connection.request("GET", "/api/v1/admin/session")
        return connection.getresponse().status
    except (OSError, http.client.HTTPException):
        return 0
    finally:
        connection.close()


def wait_for_session(origin: str, timeout: float) -> tuple[float, list[int]]:
    started = time.monotonic()
    observed = []
    while time.monotonic() - started < timeout:
        observed.append(session_status(origin))
        if observed[-1] == 401:
            return time.monotonic() - started, observed
        time.sleep(0.5)
    raise RuntimeError(f"Gateway did not recover within {timeout}s; statuses={observed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--origin", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.project.startswith("frameread-s0-"):
        raise ValueError("Only isolated frameread-s0-* acceptance projects are supported")
    api_name = f"{args.project}-api-admin-1"
    gateway_name = f"{args.project}-gateway-1"
    network_name = f"{args.project}_internal"
    api = inspect("container", api_name)
    if api["Config"]["Labels"]["com.docker.compose.project"] != args.project:
        raise RuntimeError("Acceptance project identity mismatch")
    original = api["NetworkSettings"]["Networks"][network_name]
    network = inspect("network", network_name)
    subnet = ipaddress.ip_network(network["IPAM"]["Config"][0]["Subnet"])
    changed_ip = str(subnet.broadcast_address - 2)
    assigned = {item["IPv4Address"].split("/")[0] for item in network["Containers"].values()}
    if changed_ip in assigned or changed_ip == original["IPAddress"]:
        raise RuntimeError("Acceptance target address is already in use")
    gateway_before = inspect("container", gateway_name)
    wait_for_session(args.origin, 20)
    try:
        docker("network", "disconnect", network_name, api_name)
        docker("network", "connect", "--ip", changed_ip, "--alias", "api-admin", network_name, api_name)
        elapsed, statuses = wait_for_session(args.origin, 20)
        gateway_after = inspect("container", gateway_name)
        assert gateway_after["Id"] == gateway_before["Id"]
        assert gateway_after["State"]["StartedAt"] == gateway_before["State"]["StartedAt"]
        result = {
            "original_api_ip": original["IPAddress"],
            "changed_api_ip": changed_ip,
            "recovered_in_seconds": round(elapsed, 3),
            "statuses": statuses,
            "gateway_restarted": False,
        }
    finally:
        current = inspect("container", api_name)["NetworkSettings"]["Networks"].get(network_name)
        if current is None or current["IPAddress"] != original["IPAddress"]:
            if current is not None:
                docker("network", "disconnect", network_name, api_name)
            docker("network", "connect", "--ip", original["IPAddress"], "--alias", "api-admin", network_name, api_name)
        wait_for_session(args.origin, 20)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
