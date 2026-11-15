import pytest
from sqlalchemy import select

from frameread.db.models import instance_state
from frameread.db.repository import versioned_update
from frameread.db.uow import UnitOfWork
from frameread.domain.errors import AppError, ErrorCode

pytestmark = pytest.mark.integration


def read(uow):
    c = instance_state.c
    return uow.execute(select(c.version, c.config_revision)).one()


def test_matching_version_updates_and_increments(migrated_db):
    engine = migrated_db.app_engine()
    with UnitOfWork(engine) as uow:
        before = read(uow)
        stmt = versioned_update(instance_state, instance_state.c.singleton_key == 1, before.version, config_revision=7)
        uow.execute_one(stmt)
        uow.commit()
    with UnitOfWork(engine) as uow:
        after = read(uow)
    assert (after.version, after.config_revision) == (before.version + 1, 7)
    engine.dispose()


def test_stale_version_raises_conflict_and_leaves_row_unchanged(migrated_db):
    engine = migrated_db.app_engine()
    with UnitOfWork(engine) as uow:
        before = read(uow)
        stmt = versioned_update(
            instance_state, instance_state.c.singleton_key == 1, before.version + 5, config_revision=7
        )
        with pytest.raises(AppError) as exc:
            uow.execute_one(stmt)
    assert exc.value.code is ErrorCode.VERSION_CONFLICT
    with UnitOfWork(engine) as uow:
        assert read(uow) == before
    engine.dispose()


def test_versioned_update_rejects_manual_version_value(migrated_db):
    with pytest.raises(ValueError):
        versioned_update(instance_state, instance_state.c.singleton_key == 1, 1, version=9)
