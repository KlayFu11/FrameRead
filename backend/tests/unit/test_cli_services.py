import json
import os
import subprocess
import sysconfig
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from frameread.cli.main import app
from frameread.observability.liveness import HEARTBEAT_DIR_ENV, main, touch_heartbeat

runner = CliRunner()


def test_installed_health_live_checks_heartbeat_within_container_timeout(heartbeat_dir):
    executable = Path(sysconfig.get_path("scripts")) / ("frameread.exe" if os.name == "nt" else "frameread")
    # 可执行文件来自当前解释器的安装目录，参数均为测试常量，不执行 shell。
    command = [str(executable), "health", "live", "--name", "worker"]
    missing = subprocess.run(command, capture_output=True, timeout=3, check=False)  # noqa: S603
    assert missing.returncode == 1, missing.stderr.decode()
    touch_heartbeat(heartbeat_dir, "worker")
    live = subprocess.run(command, capture_output=True, timeout=3, check=False)  # noqa: S603
    assert live.returncode == 0, live.stderr.decode()
    old = time.time() - 120
    os.utime(heartbeat_dir / "worker.alive", (old, old))
    stale = subprocess.run(command, capture_output=True, timeout=3, check=False)  # noqa: S603
    assert stale.returncode == 1, stale.stderr.decode()


@pytest.fixture
def heartbeat_dir(tmp_path: Path, monkeypatch) -> Path:
    hb = tmp_path / "hb"
    monkeypatch.setenv(HEARTBEAT_DIR_ENV, str(hb))
    return hb


def test_live_fails_without_heartbeat(heartbeat_dir):
    assert main(["--name", "worker"]) == 1


def test_live_passes_after_service_heartbeat(heartbeat_dir):
    touch_heartbeat(heartbeat_dir, "worker")
    assert main(["--name", "worker"]) == 0
    assert main(["--name", "control"]) == 1


def test_live_fails_with_stale_heartbeat(heartbeat_dir):
    touch_heartbeat(heartbeat_dir, "control")
    old = time.time() - 120
    os.utime(heartbeat_dir / "control.alive", (old, old))
    assert main(["--name", "control", "--max-age", "30"]) == 1


def test_live_rejects_unknown_process_name(heartbeat_dir):
    with pytest.raises(SystemExit) as exc:
        main(["--name", "api"])
    assert exc.value.code == 2


def test_openapi_export_is_deterministic_and_hides_internal_health(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert runner.invoke(app, ["openapi", "export", "--out", str(a)]).exit_code == 0
    assert runner.invoke(app, ["openapi", "export", "--out", str(b)]).exit_code == 0
    assert a.read_bytes() == b.read_bytes()
    spec = json.loads(a.read_text(encoding="utf-8"))
    assert spec["info"]["title"] == "FrameRead Admin API"
    assert not any(path.startswith("/health") for path in spec["paths"])


def test_openapi_export_rejects_unknown_app(tmp_path):
    result = runner.invoke(app, ["openapi", "export", "--app", "public", "--out", str(tmp_path / "x.json")])
    assert result.exit_code == 2
