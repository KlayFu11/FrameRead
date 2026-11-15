from pathlib import Path
from urllib.parse import urlsplit

from frameread.settings import load_config

DEPLOY_SETTINGS = Path(__file__).resolve().parents[3] / "deploy" / "settings.toml"


def test_production_settings_load_and_policy_is_valid():
    config = load_config(DEPLOY_SETTINGS)
    assert config.policy.pools["video"].execution_slots >= 1


def test_production_admin_origins_only_allow_http_on_8080_or_https():
    # 生产配置中不得出现非 8080 的 http origin，例如 Vite 开发源（Q38、M01 §3.9 条 71）
    for origin in load_config(DEPLOY_SETTINGS).admin.origins:
        parts = urlsplit(origin)
        assert parts.scheme in ("http", "https"), origin
        if parts.scheme == "http":
            assert parts.port == 8080, origin
            assert parts.hostname in ("127.0.0.1", "localhost"), origin
        assert parts.path in ("", "/") and not parts.query, origin
