from datetime import timedelta

import pytest
from sqlalchemy import insert, select, update
from typer.testing import CliRunner

from frameread.cli.main import app
from frameread.db.models import admin_sessions, instance_state
from frameread.db.uow import UnitOfWork

from . import test_admin_health

admin_env = test_admin_health.admin_env

pytestmark = pytest.mark.integration


def test_control_cleanup_physically_removes_only_sessions_expired_over_a_day(migrated_db, admin_env):
    admin_env(migrated_db.app_dsn)
    engine = migrated_db.app_engine()
    with UnitOfWork(engine) as uow:
        now = uow.db_now()
        for index, age in enumerate((2, 3, 0.5, -1)):
            uow.execute(
                insert(admin_sessions).values(
                    token_hash=bytes([index]) * 32,
                    csrf_hash=bytes(32),
                    credential_generation="a" * 16,
                    expires_at=now - timedelta(days=age),
                    last_seen_at=now,
                    deleted_at=now if index == 1 else None,
                )
            )
        uow.commit()
    result = CliRunner().invoke(app, ["control", "cleanup-sessions"])
    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        rows = conn.execute(select(admin_sessions)).all()
    engine.dispose()
    assert len(rows) == 2
    assert all(row.expires_at > now - timedelta(days=1) for row in rows)


@pytest.mark.parametrize("mode,restore", [("frozen", "normal"), ("normal", "review_required")])
def test_control_cleanup_defers_during_write_freeze(migrated_db, admin_env, mode, restore):
    admin_env(migrated_db.app_dsn)
    engine = migrated_db.app_engine()
    with UnitOfWork(engine) as uow:
        now = uow.db_now()
        uow.execute(
            insert(admin_sessions).values(
                token_hash=bytes(32),
                csrf_hash=bytes(32),
                credential_generation="a" * 16,
                expires_at=now - timedelta(days=3),
                last_seen_at=now,
            )
        )
        uow.execute(update(instance_state).values(maintenance_mode=mode, restore_state=restore))
        uow.commit()
    result = CliRunner().invoke(app, ["control", "cleanup-sessions"])
    assert result.exit_code == 0
    with engine.connect() as conn:
        assert len(conn.execute(select(admin_sessions)).all()) == 1
    engine.dispose()
