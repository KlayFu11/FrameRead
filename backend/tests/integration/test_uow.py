import asyncio
import threading
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from frameread.db.engine import make_async_engine
from frameread.db.uow import AsyncUnitOfWork, LockMode, UnitOfWork, run_transaction
from frameread.domain.errors import AppError, ErrorCode
from frameread.domain.gate import GateOp

pytestmark = pytest.mark.integration


@pytest.fixture
def migrated(migrated_db):
    return migrated_db


def set_mode(db, maintenance="normal", restore="normal"):
    su = create_engine(db.superuser_dsn)
    with su.begin() as conn:
        conn.execute(
            text("UPDATE instance_state SET maintenance_mode = :m, restore_state = :r"),
            {"m": maintenance, "r": restore},
        )
    su.dispose()


def test_gate_requires_lock_first(migrated):
    engine = migrated.app_engine()
    with UnitOfWork(engine) as uow, pytest.raises(RuntimeError):
        uow.gate.require(GateOp.ADMIT)
    engine.dispose()


@pytest.mark.parametrize(
    ("maintenance", "restore"),
    [("draining", "normal"), ("frozen", "normal"), ("normal", "review_required")],
)
def test_admit_rejected_outside_normal(migrated, maintenance, restore):
    set_mode(migrated, maintenance, restore)
    engine = migrated.app_engine()
    with UnitOfWork(engine) as uow:
        uow.lock_instance(LockMode.UPDATE)
        with pytest.raises(AppError) as exc:
            uow.gate.require(GateOp.ADMIT)
    assert exc.value.code is ErrorCode.MAINTENANCE
    engine.dispose()


def test_lock_instance_twice_is_rejected(migrated):
    engine = migrated.app_engine()
    with UnitOfWork(engine) as uow:
        uow.lock_instance(LockMode.SHARE)
        with pytest.raises(RuntimeError):
            uow.lock_instance(LockMode.UPDATE)
    engine.dispose()


def test_lock_instance_reads_policy_and_db_now_advances(migrated):
    engine = migrated.app_engine()
    with UnitOfWork(engine) as uow:
        inst = uow.lock_instance(LockMode.UPDATE)
        t1 = uow.db_now()
        t2 = uow.db_now()
    assert inst.policy.pools["video"].execution_slots == 2
    assert isinstance(t1, datetime) and t2 > t1
    engine.dispose()


def test_uncommitted_uow_rolls_back(migrated):
    engine = migrated.app_engine()
    with UnitOfWork(engine) as uow:
        uow.execute(text("UPDATE instance_state SET config_revision = 99"))
    with UnitOfWork(engine) as uow:
        assert uow.execute(text("SELECT config_revision FROM instance_state")).scalar_one() == 1
    engine.dispose()


def test_async_uow_gate_and_commit(migrated):
    async def scenario():
        engine = make_async_engine(migrated.app_dsn, pool_size=2, pool_timeout=5)
        try:
            async with AsyncUnitOfWork(engine) as uow:
                inst = await uow.lock_instance(LockMode.UPDATE)
                uow.gate.require(GateOp.CONFIG_WRITE)
                await uow.execute(text("UPDATE instance_state SET config_revision = config_revision + 1"))
                await uow.commit()
            async with AsyncUnitOfWork(engine) as uow:
                rev = (await uow.execute(text("SELECT config_revision FROM instance_state"))).scalar_one()
            return inst, rev
        finally:
            await engine.dispose()

    inst, rev = asyncio.run(scenario())
    assert rev == inst.config_revision + 1


@pytest.fixture
def two_rows(migrated):
    su = create_engine(migrated.superuser_dsn)
    with su.begin() as conn:
        conn.execute(text("CREATE TABLE deadlock_probe (id int PRIMARY KEY, v int NOT NULL)"))
        conn.execute(text("INSERT INTO deadlock_probe VALUES (1, 0), (2, 0)"))
        conn.execute(text("GRANT SELECT, UPDATE ON deadlock_probe TO frameread_app"))
    su.dispose()
    return migrated


def test_run_transaction_retries_real_deadlock(two_rows):
    engine = two_rows.app_engine()
    barrier = threading.Barrier(2, timeout=10)
    attempts = {"a": 0, "b": 0}
    errors: list[BaseException] = []

    def txn(name, first, second):
        def fn(uow):
            attempts[name] += 1
            uow.execute(text("UPDATE deadlock_probe SET v = v + 1 WHERE id = :i"), {"i": first})
            if attempts[name] == 1:
                barrier.wait()  # 两个事务各持一行后交叉申请，制造真实死锁
            uow.execute(text("UPDATE deadlock_probe SET v = v + 1 WHERE id = :i"), {"i": second})

        try:
            run_transaction(engine, fn)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=txn, args=("a", 1, 2)), threading.Thread(target=txn, args=("b", 2, 1))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert sorted(attempts.values()) == [1, 2]
    with UnitOfWork(engine) as uow:
        assert uow.execute(text("SELECT sum(v) FROM deadlock_probe")).scalar_one() == 4
    engine.dispose()


def test_run_transaction_does_not_retry_other_errors(migrated):
    engine = migrated.app_engine()
    calls = 0

    def fn(uow):
        nonlocal calls
        calls += 1
        uow.execute(text("UPDATE instance_state SET version = 0"))

    with pytest.raises(DBAPIError) as exc:
        run_transaction(engine, fn)
    assert exc.value.orig.sqlstate == "23514"
    assert calls == 1
    engine.dispose()
