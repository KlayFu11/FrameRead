import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import structlog
from sqlalchemy import Connection, DateTime, Executable, Result, Select, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from frameread.db.models import instance_state
from frameread.domain.errors import AppError, ErrorCode
from frameread.domain.gate import GateOp, MaintenanceMode, RestoreState, is_allowed
from frameread.domain.policy import ResourcePolicy

RETRYABLE_SQLSTATES = frozenset({"40001", "40P01"})
MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.05
_BACKOFF_CAP = 0.5
_log = structlog.get_logger()


class CommitOutcomeUnknown(Exception):
    """COMMIT 期间连接中断，无法判断事务是否已提交；不得重跑（Q10）。"""


class LockMode(StrEnum):
    UPDATE = "update"
    SHARE = "share"


@dataclass(frozen=True)
class InstanceRow:
    installation_id: UUID
    instance_epoch: UUID
    maintenance_mode: MaintenanceMode
    restore_state: RestoreState
    policy: ResourcePolicy
    config_revision: int


# lease 等判定只用数据库时间，不用工作进程本地时钟（SPEC §10.1）
_DB_NOW: Select[tuple[datetime]] = select(func.clock_timestamp(type_=DateTime(timezone=True)))


def sqlstate_of(exc: BaseException) -> str | None:
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


def backoff_seconds(attempt: int) -> float:
    # full jitter：0 ~ min(上限, 基数×2ⁿ)
    return random.uniform(0, min(_BACKOFF_CAP, _BACKOFF_BASE * 2**attempt))  # noqa: S311


def _instance_query(mode: LockMode) -> Select[Any]:
    c = instance_state.c
    return (
        select(
            c.installation_id, c.instance_epoch, c.maintenance_mode, c.restore_state, c.policy_json, c.config_revision
        )
        .where(c.singleton_key == 1)
        .with_for_update(read=mode is LockMode.SHARE)
    )


def _to_instance(row: Any) -> InstanceRow:
    if row is None:
        raise RuntimeError("instance_state 未初始化")
    return InstanceRow(
        installation_id=row.installation_id,
        instance_epoch=row.instance_epoch,
        maintenance_mode=MaintenanceMode(row.maintenance_mode),
        restore_state=RestoreState(row.restore_state),
        policy=ResourcePolicy.model_validate(row.policy_json),
        config_revision=row.config_revision,
    )


def _require_one_row(result: Result[Any]) -> None:
    rowcount = result.rowcount  # type: ignore[attr-defined]
    if rowcount == 0:
        raise AppError(ErrorCode.VERSION_CONFLICT)
    if rowcount != 1:
        raise RuntimeError(f"条件更新预期影响 1 行，实际 {rowcount} 行")


def _commit_failure(exc: DBAPIError) -> Exception:
    # 服务端回了 SQLSTATE 说明事务已明确结束；没有 SQLSTATE 是连接层中断，结果未知
    if sqlstate_of(exc) is None:
        _log.warning("commit_failed", commit_outcome="unknown")
        return CommitOutcomeUnknown()
    _log.warning("commit_failed", commit_outcome="rolled_back")
    return exc


class Gate:
    """写入门禁：必须在同一事务已锁定的实例行上判定（SPEC §7.1）。"""

    def __init__(self) -> None:
        self._instance: InstanceRow | None = None

    def bind(self, instance: InstanceRow) -> None:
        self._instance = instance

    def require(self, op: GateOp) -> InstanceRow:
        if self._instance is None:
            raise RuntimeError("gate.require 之前必须先 lock_instance")
        inst = self._instance
        if not is_allowed(op, inst.maintenance_mode, inst.restore_state):
            raise AppError(ErrorCode.MAINTENANCE)
        return inst


class _UowBase:
    def __init__(self) -> None:
        self.gate = Gate()
        self._locked = False
        self._committed = False

    def _mark_locked(self) -> None:
        # 锁模式在事务开始时确定，禁止先 SHARE 后升级 UPDATE（SPEC §7.1）
        if self._locked:
            raise RuntimeError("同一事务只能锁定一次实例行")
        self._locked = True


class UnitOfWork(_UowBase):
    """同步 UoW（Worker、control、CLI）。"""

    def __init__(self, engine: Engine) -> None:
        super().__init__()
        self._engine = engine
        self._conn: Connection | None = None

    def __enter__(self) -> Self:
        self._conn = self._engine.connect()
        self._conn.begin()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        conn = self.conn
        try:
            if not self._committed and conn.in_transaction():
                if exc is not None and isinstance(exc, DBAPIError):
                    _log.info("transaction_aborted", commit_outcome="rolled_back")
                conn.rollback()
        except DBAPIError:
            conn.invalidate()
        finally:
            conn.close()

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("UnitOfWork 未进入")
        return self._conn

    def execute(self, stmt: Executable, params: Any = None) -> Result[Any]:
        return self.conn.execute(stmt, params)

    def execute_one(self, stmt: Executable, params: Any = None) -> None:
        """执行恰好影响一行的条件更新；0 行即版本或状态冲突（Q9、SPEC §7.2）。"""
        _require_one_row(self.conn.execute(stmt, params))

    def lock_instance(self, mode: LockMode) -> InstanceRow:
        self._mark_locked()
        inst = _to_instance(self.conn.execute(_instance_query(mode)).first())
        self.gate.bind(inst)
        return inst

    def db_now(self) -> datetime:
        return self.conn.execute(_DB_NOW).scalar_one()

    def commit(self) -> None:
        try:
            self.conn.commit()
        except DBAPIError as exc:
            raise _commit_failure(exc) from exc
        self._committed = True


class AsyncUnitOfWork(_UowBase):
    """异步 UoW（API）；方法与 UnitOfWork 一一对应。"""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__()
        self._engine = engine
        self._conn: AsyncConnection | None = None

    async def __aenter__(self) -> Self:
        self._conn = await self._engine.connect()
        await self._conn.begin()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        conn = self.conn
        try:
            if not self._committed and conn.in_transaction():
                if exc is not None and isinstance(exc, DBAPIError):
                    _log.info("transaction_aborted", commit_outcome="rolled_back")
                await conn.rollback()
        except DBAPIError:
            await conn.invalidate()
        finally:
            await conn.close()

    @property
    def conn(self) -> AsyncConnection:
        if self._conn is None:
            raise RuntimeError("AsyncUnitOfWork 未进入")
        return self._conn

    async def execute(self, stmt: Executable, params: Any = None) -> Result[Any]:
        return await self.conn.execute(stmt, params)

    async def execute_one(self, stmt: Executable, params: Any = None) -> None:
        _require_one_row(await self.conn.execute(stmt, params))

    async def lock_instance(self, mode: LockMode) -> InstanceRow:
        self._mark_locked()
        inst = _to_instance((await self.conn.execute(_instance_query(mode))).first())
        self.gate.bind(inst)
        return inst

    async def db_now(self) -> datetime:
        return (await self.conn.execute(_DB_NOW)).scalar_one()

    async def commit(self) -> None:
        try:
            await self.conn.commit()
        except DBAPIError as exc:
            raise _commit_failure(exc) from exc
        self._committed = True


def run_transaction[T](engine: Engine, fn: Callable[[UnitOfWork], T]) -> T:
    """整体重跑无外部副作用的短事务：仅 40001/40P01，总计最多 3 次（D06）。"""
    for attempt in range(MAX_ATTEMPTS):
        try:
            with UnitOfWork(engine) as uow:
                result = fn(uow)
                uow.commit()
                return result
        except DBAPIError as exc:
            if sqlstate_of(exc) not in RETRYABLE_SQLSTATES or attempt == MAX_ATTEMPTS - 1:
                raise
        time.sleep(backoff_seconds(attempt))
    raise AssertionError("unreachable")


async def run_transaction_async[T](engine: AsyncEngine, fn: Callable[[AsyncUnitOfWork], Awaitable[T]]) -> T:
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with AsyncUnitOfWork(engine) as uow:
                result = await fn(uow)
                await uow.commit()
                return result
        except DBAPIError as exc:
            if sqlstate_of(exc) not in RETRYABLE_SQLSTATES or attempt == MAX_ATTEMPTS - 1:
                raise
        await asyncio.sleep(backoff_seconds(attempt))
    raise AssertionError("unreachable")
