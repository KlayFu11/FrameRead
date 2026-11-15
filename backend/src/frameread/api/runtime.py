import asyncio
import hmac
import os
from dataclasses import dataclass, field

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request

from frameread.db.bootstrap import (
    FatalStartupError,
    RuntimeIdentity,
    StartupError,
    database_head,
    expected_head,
    verify_startup,
)
from frameread.db.models import instance_state
from frameread.domain.errors import AppError, ErrorCode
from frameread.observability.health import HealthRegistry, ProbeFailed, Severity
from frameread.security.crypto import root_key_check

STARTUP_RETRY_SECONDS = 2.0
_log = structlog.get_logger()


@dataclass
class AdminRuntime:
    """api-admin 进程级依赖；identity 在启动校验通过前为 None，期间拒绝业务写入。"""

    engine: AsyncEngine
    redis: Redis
    root_key: bytes
    health: HealthRegistry = field(default_factory=HealthRegistry)
    identity: RuntimeIdentity | None = None

    def __post_init__(self) -> None:
        self.health.register_probe("postgres", self._probe_postgres, Severity.CRITICAL)
        self.health.register_probe("migration_head", self._probe_migration_head, Severity.CRITICAL)
        self.health.register_probe("root_key", self._probe_root_key, Severity.CRITICAL)
        self.health.register_probe("redis", self._probe_redis, Severity.DEGRADED)

    async def try_establish(self) -> bool:
        """执行一次启动校验；可重试的失败返回 False，根密钥不符等致命错误直接抛出。"""
        try:
            async with self.engine.connect() as conn:
                self.identity = await conn.run_sync(verify_startup, self.root_key)
        except FatalStartupError:
            raise
        except (StartupError, DBAPIError, OSError):
            _log.warning("startup_not_ready")
            return False
        _log.info("startup_verified", epoch=str(self.identity.instance_epoch))
        return True

    async def establish_forever(self) -> None:
        # 固定间隔重连数据库，不依赖 compose depends_on（SPEC §19）
        while not await self._establish_or_exit():  # noqa: ASYNC110
            await asyncio.sleep(STARTUP_RETRY_SECONDS)

    async def _establish_or_exit(self) -> bool:
        try:
            return await self.try_establish()
        except FatalStartupError:
            # 后台重试中发现致命错误：进程以非零码退出，不继续服务（SPEC §19）
            _log.critical("startup_fatal")
            os._exit(1)

    async def _probe_postgres(self) -> None:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(select(1))
        except (DBAPIError, OSError):
            raise ProbeFailed("connection_failed") from None

    async def _probe_migration_head(self) -> None:
        try:
            async with self.engine.connect() as conn:
                head = await conn.run_sync(database_head)
        except (DBAPIError, OSError):
            raise ProbeFailed("connection_failed") from None
        if head != expected_head():
            raise ProbeFailed("head_mismatch")

    async def _probe_root_key(self) -> None:
        if self.identity is None:
            raise ProbeFailed("not_verified")
        try:
            async with self.engine.connect() as conn:
                stored = (
                    await conn.execute(
                        select(instance_state.c.root_key_check).where(instance_state.c.singleton_key == 1)
                    )
                ).scalar_one_or_none()
        except (DBAPIError, OSError):
            raise ProbeFailed("connection_failed") from None
        if stored is None or not hmac.compare_digest(bytes(stored), root_key_check(self.root_key)):
            raise ProbeFailed("mismatch")

    async def _probe_redis(self) -> None:
        try:
            await self.redis.ping()
        except (RedisError, OSError):
            raise ProbeFailed("connection_failed") from None


def require_runtime(request: Request) -> AdminRuntime:
    """业务路由依赖：启动校验未通过时拒绝写入（D04）。"""
    runtime: AdminRuntime = request.app.state.runtime
    if runtime.identity is None:
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE)
    return runtime
