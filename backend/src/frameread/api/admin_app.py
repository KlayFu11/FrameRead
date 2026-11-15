import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from frameread.api.errors import install_error_handling
from frameread.api.runtime import AdminRuntime
from frameread.db.bootstrap import parse_root_key
from frameread.db.engine import make_async_engine
from frameread.observability.logging import configure_logging
from frameread.settings import API_ADMIN_CONNECTIONS, AdminSecrets, AppConfig, load_config, load_secrets

_REDIS_TIMEOUT_SECONDS = 2


class LiveBody(BaseModel):
    status: Literal["live"]


class CheckBody(BaseModel):
    name: str
    status: str
    observed_at: datetime | None
    detail: str | None = None


class ReadyBody(BaseModel):
    status: str
    checks: list[CheckBody]


def build_runtime(config: AppConfig, secrets: AdminSecrets) -> AdminRuntime:
    engine = make_async_engine(
        secrets.secret("database_dsn_file"),
        pool_size=API_ADMIN_CONNECTIONS,
        pool_timeout=config.runtime.pool_timeout_seconds,
    )
    redis = Redis.from_url(
        secrets.secret("redis_url_file"),
        socket_timeout=_REDIS_TIMEOUT_SECONDS,
        socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
    )
    return AdminRuntime(engine=engine, redis=redis, root_key=parse_root_key(secrets.secret("master_key_file")))


def create_app() -> FastAPI:
    """api-admin 入口（uvicorn --factory）。配置或密钥缺失时启动即失败。"""
    configure_logging()
    config = load_config()
    secrets = load_secrets(AdminSecrets)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = build_runtime(config, secrets)
        app.state.runtime = runtime
        retry: asyncio.Task[None] | None = None
        # 首次校验遇到根密钥不符直接抛出，进程启动失败；数据库未就绪则后台重试
        if not await runtime.try_establish():
            retry = asyncio.create_task(runtime.establish_forever())
        try:
            yield
        finally:
            if retry is not None:
                retry.cancel()
            await runtime.redis.aclose()
            await runtime.engine.dispose()

    app = build_app(lifespan)
    app.state.config = config
    return app


def build_app(lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None) -> FastAPI:
    """装配路由与错误处理；不加载配置，OpenAPI 导出直接使用。"""
    app = FastAPI(title="FrameRead Admin API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    install_error_handling(app)

    # 内部健康接口：只在容器内网可达，gateway 不转发（R3）
    @app.get("/health/live", include_in_schema=False)
    async def live() -> LiveBody:
        return LiveBody(status="live")

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        report = await request.app.state.runtime.health.report()
        body = ReadyBody(
            status=report.status,
            checks=[
                CheckBody(name=c.name, status=c.status, observed_at=c.observed_at, detail=c.detail)
                for c in report.checks
            ],
        )
        return JSONResponse(body.model_dump(mode="json"), status_code=report.http_status)

    return app
