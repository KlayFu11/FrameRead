from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# 连接获取超时明确失败；max_overflow 固定为 0，连接预算可静态核算（SPEC §7）
_CONNECT_TIMEOUT_SECONDS = 5


def make_engine(dsn: str, *, pool_size: int, pool_timeout: float) -> Engine:
    return create_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=0,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )


def make_async_engine(dsn: str, *, pool_size: int, pool_timeout: float) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=0,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )
