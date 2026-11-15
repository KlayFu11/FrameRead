from pathlib import Path

import pytest
from pydantic import ValidationError

from frameread.domain.policy import ResourcePolicy
from frameread.settings import (
    AppConfig,
    ConfigError,
    DeploymentScale,
    connection_budget,
    load_config,
    read_secret,
)

MINIMAL_TOML = """
[admin]
origins = ["http://127.0.0.1:8080", "http://localhost:8080"]

[policy.pools.video]
execution_slots = 2
waiting_slots = 4
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_policy_defaults_follow_d08():
    p = ResourcePolicy.model_validate({"pools": {"video": {"execution_slots": 2, "waiting_slots": 4}}})
    assert p.video_total_timeout_seconds == 7200
    assert (p.lease_seconds, p.heartbeat_seconds) == (60, 10)
    assert (p.dispatcher_batch, p.dispatch_retry_budget, p.dispatch_generation_limit) == (50, 10, 5)
    assert p.event_retention_days == 7


@pytest.mark.parametrize(
    "bad",
    [
        {"pools": {}},
        {"pools": {"video": {"execution_slots": 0, "waiting_slots": 4}}},
        {"pools": {"video": {"execution_slots": 2, "waiting_slots": -1}}},
        {
            "pools": {
                "audio": {"execution_slots": 1, "waiting_slots": 1},
                "video": {"execution_slots": 1, "waiting_slots": 1},
            }
        },
        {"pools": {"video": {"execution_slots": 2, "waiting_slots": 4}}, "heartbeat_seconds": 60},
        {"pools": {"video": {"execution_slots": 2, "waiting_slots": 4}}, "unknown_key": 1},
        {"pools": {"video": {"execution_slots": "2", "waiting_slots": 4}}},
    ],
)
def test_policy_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        ResourcePolicy.model_validate(bad)


def test_load_config_from_toml(tmp_path):
    cfg = load_config(write(tmp_path, "settings.toml", MINIMAL_TOML))
    assert isinstance(cfg, AppConfig)
    assert cfg.admin.origins == ["http://127.0.0.1:8080", "http://localhost:8080"]
    assert cfg.policy.pools["video"].execution_slots == 2
    assert cfg.deployment == DeploymentScale()


def test_load_config_rejects_unknown_section(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "settings.toml", MINIMAL_TOML + "\n[typo]\nx = 1\n"))


def test_read_secret_strips_only_trailing_newline(tmp_path):
    assert read_secret(write(tmp_path, "k", "abc\n"), "MASTER_KEY_FILE") == "abc"
    assert read_secret(write(tmp_path, "k2", " a b \n"), "MASTER_KEY_FILE") == " a b "


@pytest.mark.parametrize("content", ["", "\n"])
def test_read_secret_empty_fails_without_leaking_content(tmp_path, content):
    with pytest.raises(ConfigError, match="MASTER_KEY_FILE"):
        read_secret(write(tmp_path, "k", content), "MASTER_KEY_FILE")


def test_read_secret_missing_fails_with_setting_name(tmp_path):
    with pytest.raises(ConfigError, match="DATABASE_DSN_FILE"):
        read_secret(tmp_path / "nope", "DATABASE_DSN_FILE")


def test_connection_budget_formula():
    # API×5 + Worker 并发×2 + control×3 + 保留 5
    scale = DeploymentScale(api_admin_instances=2, worker_concurrency=3, control_instances=1)
    assert connection_budget(scale) == 2 * 5 + 3 * 2 + 1 * 3 + 5
