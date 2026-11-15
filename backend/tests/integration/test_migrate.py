import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from frameread.db.bootstrap import (
    FatalStartupError,
    SchemaNotReady,
    StartupError,
    database_head,
    expected_head,
    run_migrations,
    verify_startup,
)
from frameread.security.crypto import KeyPurpose
from frameread.settings import DeploymentScale

from .conftest import POLICY, ROOT_KEY, SCALE

pytestmark = pytest.mark.integration


def migrate(db, *, root_key=ROOT_KEY, scale=SCALE, policy=POLICY):
    engine = db.migrate_engine()
    try:
        with engine.connect() as conn:
            run_migrations(conn, scale=scale, policy=policy, root_key=root_key)
    finally:
        engine.dispose()


def instance(db):
    engine = db.migrate_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM instance_state")).mappings().all()
    engine.dispose()
    return row


def test_empty_database_migrates_and_initializes_instance(fresh_db):
    migrate(fresh_db)
    (row,) = instance(fresh_db)
    assert row["singleton_key"] == 1
    assert row["maintenance_mode"] == "normal" and row["restore_state"] == "normal"
    assert row["policy_json"] == POLICY.model_dump(mode="json")
    assert row["config_revision"] == 1 and row["version"] == 1
    assert isinstance(row["installation_id"], uuid.UUID) and isinstance(row["instance_epoch"], uuid.UUID)
    engine = fresh_db.app_engine()
    with engine.connect() as conn:
        assert database_head(conn) == expected_head()
    engine.dispose()


def test_second_migrate_keeps_identity_and_epoch(fresh_db):
    migrate(fresh_db)
    (first,) = instance(fresh_db)
    migrate(fresh_db)
    (second,) = instance(fresh_db)
    assert first == second


def test_singleton_rejects_second_row(fresh_db):
    migrate(fresh_db)
    engine = fresh_db.migrate_engine()
    with engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO instance_state (singleton_key, installation_id, instance_epoch, restore_state,"
                " maintenance_mode, policy_json, config_revision, root_key_check)"
                " SELECT 2, installation_id, instance_epoch, restore_state, maintenance_mode, policy_json,"
                " config_revision, root_key_check FROM instance_state"
            )
        )
    engine.dispose()


def test_app_role_cannot_insert_or_delete_instance(fresh_db):
    migrate(fresh_db)
    engine = fresh_db.app_engine()
    with engine.connect() as conn, pytest.raises(DBAPIError) as exc:
        conn.execute(text("DELETE FROM instance_state"))
    assert exc.value.orig.sqlstate == "42501"
    engine.dispose()


def test_migrate_with_different_root_key_fails_without_changing_instance(fresh_db):
    migrate(fresh_db)
    before = instance(fresh_db)
    with pytest.raises(FatalStartupError):
        migrate(fresh_db, root_key=bytes(32))
    assert instance(fresh_db) == before


def test_connection_budget_exceeding_max_connections_fails_before_schema_change(fresh_db):
    huge = DeploymentScale(api_admin_instances=1000)
    with pytest.raises(StartupError, match="连接预算"):
        migrate(fresh_db, scale=huge)
    engine = fresh_db.migrate_engine()
    with engine.connect() as conn:
        assert database_head(conn) is None
        assert conn.execute(text("SELECT to_regclass('instance_state')")).scalar_one() is None
    engine.dispose()


def test_concurrent_migrate_serializes_on_advisory_lock(fresh_db):
    errors: list[BaseException] = []
    start = threading.Barrier(2)

    def worker():
        try:
            start.wait()
            migrate(fresh_db)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert errors == []
    assert len(instance(fresh_db)) == 1


def test_updated_at_trigger_and_version_rules(fresh_db):
    migrate(fresh_db)
    engine = fresh_db.app_engine()
    with engine.begin() as conn:
        before = conn.execute(text("SELECT updated_at, version FROM instance_state")).one()
    with engine.begin() as conn:
        # 调用方设置的 updated_at 被触发器覆盖
        conn.execute(text("UPDATE instance_state SET updated_at = '2000-01-01', version = version + 1"))
        after = conn.execute(text("SELECT updated_at, version FROM instance_state")).one()
    assert after.updated_at > before.updated_at
    assert after.version == before.version + 1
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE instance_state SET version = 0"))
    engine.dispose()


def test_verify_startup_derives_keys_from_installation(fresh_db):
    migrate(fresh_db)
    (row,) = instance(fresh_db)
    engine = fresh_db.app_engine()
    with engine.connect() as conn:
        ident = verify_startup(conn, ROOT_KEY)
    engine.dispose()
    assert ident.installation_id == row["installation_id"]
    assert ident.instance_epoch == row["instance_epoch"]
    assert len(ident.keyring.derive(KeyPurpose.CURSOR)) == 32


def test_verify_startup_rejects_wrong_root_key(fresh_db):
    migrate(fresh_db)
    engine = fresh_db.app_engine()
    with engine.connect() as conn, pytest.raises(FatalStartupError):
        verify_startup(conn, bytes(32))
    engine.dispose()


def test_verify_startup_reports_unmigrated_database_not_ready(fresh_db):
    engine = fresh_db.app_engine()
    with engine.connect() as conn, pytest.raises(SchemaNotReady):
        verify_startup(conn, ROOT_KEY)
    engine.dispose()


def test_verify_startup_rejects_ancestor_or_foreign_head(fresh_db):
    migrate(fresh_db)
    su = create_engine(fresh_db.superuser_dsn)
    with su.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    su.dispose()
    engine = fresh_db.app_engine()
    with engine.connect() as conn, pytest.raises(SchemaNotReady):
        verify_startup(conn, ROOT_KEY)
    engine.dispose()
