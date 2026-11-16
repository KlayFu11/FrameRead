import asyncio
import hmac
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import structlog
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from frameread.api.errors import error_response
from frameread.api.runtime import AdminRuntime, require_runtime
from frameread.api.schemas import ErrorEnvelope
from frameread.db.bootstrap import FatalStartupError
from frameread.db.models import admin_sessions
from frameread.db.uow import AsyncUnitOfWork, LockMode, UnitOfWork, run_transaction_async
from frameread.domain.errors import AppError, ErrorCode
from frameread.domain.gate import GateOp, is_allowed
from frameread.security.crypto import KeyPurpose
from frameread.security.sessions import (
    credential_generation,
    csrf_token,
    host_allowed,
    origin_allowed,
    source_hash,
    token_hash,
)

COOKIE = "frameread_admin"
COOKIE_PATH = "/api/v1/admin"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WINDOW_SECONDS = 900
ARGON2_CONCURRENCY = 2
_log = structlog.get_logger()

# 首次失败才创建固定窗口；不按成功重置，也不延长既有窗口。
_FAILURE_SCRIPT = """
local source = redis.call('INCR', KEYS[1])
if source == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local total = redis.call('INCR', KEYS[2])
if total == 1 then redis.call('EXPIRE', KEYS[2], ARGV[1]) end
return {source, total}
"""


@dataclass
class SessionSecurity:
    password_hash: str
    generation: str
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(ARGON2_CONCURRENCY))

    @classmethod
    def load(cls, path: Path) -> "SessionSecurity":
        try:
            raw = path.read_bytes()
            encoded = raw.decode("utf-8").rstrip("\r\n")
            if not encoded or extract_parameters(encoded).type is not Type.ID:
                raise ValueError
        except (OSError, UnicodeError, InvalidHashError, ValueError):
            raise FatalStartupError("ADMIN_PASSWORD_HASH_FILE 缺失、为空或不是 Argon2id hash") from None
        return cls(encoded, credential_generation(raw))


@dataclass(frozen=True)
class AdminSession:
    id: UUID
    expires_at: datetime


class PasswordLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str


class SessionResponse(BaseModel):
    csrf_token: str
    expires_at: datetime


def check_request_source(request: Request) -> None:
    origins: list[str] = request.app.state.config.admin.origins
    if not host_allowed(request.headers.get("host", ""), origins):
        raise AppError(ErrorCode.ORIGIN_REJECTED)
    if request.method in WRITE_METHODS and not origin_allowed(request.headers.get("origin"), origins):
        raise AppError(ErrorCode.ORIGIN_REJECTED)


class AdminBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(COOKIE_PATH + "/"):
            request = Request(scope)
            try:
                check_request_source(request)
                if scope["path"] == COOKIE_PATH + "/session" and request.method == "POST":
                    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type != "application/json":
                        raise AppError(ErrorCode.INVALID_INPUT)
            except AppError as exc:
                await error_response(exc.code)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _security(runtime: AdminRuntime) -> SessionSecurity:
    if runtime.session_security is None:
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE)
    return runtime.session_security


def _key(runtime: AdminRuntime) -> bytes:
    if runtime.identity is None:
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE)
    return runtime.identity.keyring.derive(KeyPurpose.SESSION_CSRF)


async def _db_transaction[T](runtime: AdminRuntime, operation: Callable[[AsyncUnitOfWork], Awaitable[T]]) -> T:
    try:
        return await run_transaction_async(runtime.engine, operation)
    except (DBAPIError, SQLTimeoutError, OSError):
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None


async def validate_admin_session(request: Request, *, check_csrf: bool = True) -> AdminSession:
    check_request_source(request)
    runtime = require_runtime(request)
    security = _security(runtime)
    token = request.cookies.get(COOKIE)
    if token is None or len(token) > 256:
        raise AppError(ErrorCode.ADMIN_REQUIRED)
    derived = csrf_token(_key(runtime), token)

    async def validate(uow: AsyncUnitOfWork) -> AdminSession:
        instance = await uow.lock_instance(LockMode.SHARE)
        now = await uow.db_now()
        c = admin_sessions.c
        row = (
            await uow.execute(
                select(admin_sessions).where(
                    c.token_hash == token_hash(token),
                    c.deleted_at.is_(None),
                    c.expires_at > now,
                    c.credential_generation == security.generation,
                )
            )
        ).first()
        if row is None:
            raise AppError(ErrorCode.ADMIN_REQUIRED)
        if check_csrf and request.method in WRITE_METHODS:
            supplied = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(supplied.encode(), derived.encode()) or not hmac.compare_digest(
                bytes(row.csrf_hash), token_hash(derived)
            ):
                raise AppError(ErrorCode.CSRF_REJECTED)
        if is_allowed(GateOp.SESSION, instance.maintenance_mode, instance.restore_state):
            await uow.execute(
                update(admin_sessions)
                .where(c.id == row.id, c.last_seen_at < now - timedelta(minutes=5))
                .values(last_seen_at=now, version=c.version + 1)
            )
        return AdminSession(id=row.id, expires_at=row.expires_at)

    result: AdminSession = await _db_transaction(runtime, validate)
    return result


async def require_admin(request: Request) -> AdminSession:
    return await validate_admin_session(request)


async def _precheck(redis: Redis, keys: list[str]) -> None:
    counts = await redis.mget(keys)
    exceeded = [
        key
        for key, value, limit in zip(keys, counts, (5, 30), strict=True)
        if value is not None and int(value) >= limit
    ]
    if exceeded:
        remaining = max([await redis.ttl(key) for key in exceeded])
        raise AppError(ErrorCode.RATE_LIMITED, retry_after_seconds=max(1, remaining))


router = APIRouter(
    prefix=COOKIE_PATH,
    tags=["session"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 422, 429, 503)},
)


@router.post("/session", status_code=201, response_model=SessionResponse, dependencies=[Depends(check_request_source)])
async def create_session(request: Request, response: Response, body: PasswordLogin) -> SessionResponse:
    runtime = require_runtime(request)
    security = _security(runtime)
    key = _key(runtime)

    async def check_gate(uow: AsyncUnitOfWork) -> None:
        await uow.lock_instance(LockMode.SHARE)
        uow.gate.require(GateOp.SESSION)

    await _db_transaction(runtime, check_gate)
    assert runtime.identity is not None
    epoch = str(runtime.identity.instance_epoch)
    source = request.client.host if request.client else "unknown"
    keys = [f"fr:{epoch}:login:{source_hash(key, source)}", f"fr:{epoch}:login:global"]
    started = time.monotonic()
    try:
        async with security.semaphore:
            queue_wait_ms = (time.monotonic() - started) * 1000
            # 排队之后再预检，确保排队中的请求不会放大阈值的在途超额。
            await _precheck(runtime.redis, keys)
            try:
                await run_in_threadpool(PasswordHasher().verify, security.password_hash, body.password)
            except VerifyMismatchError:
                await runtime.redis.eval(_FAILURE_SCRIPT, len(keys), *keys, str(WINDOW_SECONDS))
                _log.info(
                    "login_failed",
                    epoch=epoch,
                    error_code="ADMIN_REQUIRED",
                    duration_ms=(time.monotonic() - started) * 1000,
                    queue_wait_ms=queue_wait_ms,
                )
                raise AppError(ErrorCode.ADMIN_REQUIRED) from None
    except (RedisError, OSError):
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE) from None
    except AppError as exc:
        if exc.code is ErrorCode.RATE_LIMITED:
            _log.info("login_rate_limited", epoch=epoch, error_code=exc.code.value)
        raise
    token = secrets.token_urlsafe(32)
    csrf = csrf_token(key, token)

    async def create(uow: AsyncUnitOfWork) -> datetime:
        await uow.lock_instance(LockMode.SHARE)
        uow.gate.require(GateOp.SESSION)
        now = await uow.db_now()
        expiry = now + timedelta(hours=12)
        await uow.execute(
            insert(admin_sessions).values(
                token_hash=token_hash(token),
                csrf_hash=token_hash(csrf),
                credential_generation=security.generation,
                expires_at=expiry,
                last_seen_at=now,
            )
        )
        return expiry

    expiry = await _db_transaction(runtime, create)
    secure = urlsplit(request.headers["origin"]).scheme == "https"
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="strict", path=COOKIE_PATH, secure=secure, max_age=12 * 60 * 60
    )
    _log.info(
        "login_succeeded", epoch=epoch, duration_ms=(time.monotonic() - started) * 1000, queue_wait_ms=queue_wait_ms
    )
    return SessionResponse(csrf_token=csrf, expires_at=expiry)


@router.get("/session", response_model=SessionResponse)
async def read_session(request: Request, session: Annotated[AdminSession, Depends(require_admin)]) -> SessionResponse:
    return SessionResponse(
        csrf_token=csrf_token(_key(require_runtime(request)), request.cookies[COOKIE]), expires_at=session.expires_at
    )


@router.delete("/session", status_code=204)
async def logout(request: Request, session: Annotated[AdminSession, Depends(require_admin)]) -> Response:
    runtime = require_runtime(request)

    async def revoke(uow: AsyncUnitOfWork) -> None:
        await uow.lock_instance(LockMode.SHARE)
        uow.gate.require(GateOp.SESSION)
        await uow.execute(
            update(admin_sessions)
            .where(admin_sessions.c.id == session.id)
            .values(deleted_at=await uow.db_now(), version=admin_sessions.c.version + 1)
        )

    await _db_transaction(runtime, revoke)
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict")
    return response


def cleanup_expired_sessions(uow: UnitOfWork) -> int:
    instance = uow.lock_instance(LockMode.SHARE)
    if not is_allowed(GateOp.CONVERGE, instance.maintenance_mode, instance.restore_state):
        return 0
    result = uow.execute(delete(admin_sessions).where(admin_sessions.c.expires_at < uow.db_now() - timedelta(days=1)))
    return int(result.rowcount)  # type: ignore[attr-defined]


def clear_sessions_for_restore(uow: UnitOfWork) -> None:
    uow.execute(delete(admin_sessions))
