import shutil
from importlib.resources import files
from pathlib import Path

import pytest
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from frameread.db import bootstrap
from frameread.db.bootstrap import database_head, expected_head

from .test_migrate import instance, migrate

pytestmark = pytest.mark.integration

FAILING_REVISION = """# 故障注入：仅测试使用
from alembic import op

revision = "9999_fail"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE half_done (id int)")
    op.execute("SELECT 1 / 0")


def downgrade() -> None:
    raise NotImplementedError
"""


def use_failing_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, down: str) -> None:
    """复制迁移目录并追加一个会失败的 revision；生产代码与配置不改（E9）。"""
    src = Path(str(files("frameread.db") / "migrations"))
    dst = tmp_path / "migrations"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    (dst / "versions" / "9999_fail.py").write_text(FAILING_REVISION.format(down=down), encoding="utf-8")
    original = bootstrap.alembic_config

    def patched(connection=None):
        cfg = original(connection)
        cfg.set_main_option("script_location", str(dst))
        return cfg

    monkeypatch.setattr(bootstrap, "alembic_config", patched)


def test_failed_upgrade_rolls_back_ddl_and_keeps_existing_rows(fresh_db, tmp_path, monkeypatch):
    migrate(fresh_db)
    before = instance(fresh_db)
    good_head = expected_head()

    use_failing_copy(tmp_path, monkeypatch, down=good_head)
    with pytest.raises((DBAPIError, CommandError)):
        migrate(fresh_db)
    monkeypatch.undo()

    engine = fresh_db.migrate_engine()
    with engine.connect() as conn:
        assert database_head(conn) == good_head
        assert conn.execute(text("SELECT to_regclass('half_done')")).scalar_one() is None
        # 迁移锁已释放：下一次迁移不会卡住
        assert conn.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")).scalar_one() == 0
    engine.dispose()
    assert instance(fresh_db) == before


def test_failed_first_migration_leaves_empty_database(fresh_db, tmp_path, monkeypatch):
    use_failing_copy(tmp_path, monkeypatch, down=expected_head())
    with pytest.raises((DBAPIError, CommandError)):
        migrate(fresh_db)
    monkeypatch.undo()

    engine = fresh_db.migrate_engine()
    with engine.connect() as conn:
        # 整个升级在一个事务内：故障 revision 失败时，此前的 revision 也一并回滚，不留半成品 schema
        assert database_head(conn) is None
        assert conn.execute(text("SELECT to_regclass('instance_state')")).scalar_one() is None
    engine.dispose()
