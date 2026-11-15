import uuid
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from frameread.api.schemas import ErrorBody, ErrorDetailBody, ErrorEnvelope
from frameread.domain.errors import (
    DEFAULT_RETRY_AFTER_SECONDS,
    ERROR_REGISTRY,
    AppError,
    ErrorCode,
    ErrorDetail,
)

REQUEST_ID_HEADER = "X-Request-ID"
_log = structlog.get_logger()


def current_request_id() -> uuid.UUID:
    rid = structlog.contextvars.get_contextvars().get("request_id")
    if rid is None:
        raise RuntimeError("当前上下文没有 request_id")
    return uuid.UUID(rid)


def error_response(
    code: ErrorCode,
    *,
    task_id: uuid.UUID | None = None,
    details: list[ErrorDetail] | None = None,
    retry_after_seconds: int | None = None,
) -> JSONResponse:
    spec = ERROR_REGISTRY[code]
    if spec.http_status is None:
        raise ValueError(f"{code} 不是 HTTP 错误码")
    headers: dict[str, str] = {}
    retry_after: int | None = None
    if spec.http_status in (429, 503):
        retry_after = DEFAULT_RETRY_AFTER_SECONDS if retry_after_seconds is None else retry_after_seconds
        headers["Retry-After"] = str(retry_after)
    body = ErrorEnvelope(
        error=ErrorBody(
            code=code.value,
            message=spec.message,
            request_id=current_request_id(),
            task_id=task_id,
            action=spec.action.value,
            retry_after_seconds=retry_after,
            details=[ErrorDetailBody(field=d.field, code=d.code, message=d.message) for d in details or []],
        )
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=spec.http_status, headers=headers)


class RequestContextMiddleware:
    """为每个请求生成 request_id，并兜底未预期异常为 500 INTERNAL_ERROR。

    放在 Starlette ServerErrorMiddleware 内侧，保证 500 响应同样带 request_id。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 不采纳客户端传入的同名头，始终由服务端生成
        request_id = str(uuid.uuid4())
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                _log.exception("unhandled_exception", error_code=ErrorCode.INTERNAL_ERROR.value)
                if started:
                    raise
                response = error_response(ErrorCode.INTERNAL_ERROR)
                await response(scope, receive, send_with_id)


def _field_of(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return ".".join(parts) or None


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [ErrorDetail(field=_field_of(tuple(e["loc"])), code=e["type"], message=e["msg"]) for e in exc.errors()]
    return error_response(ErrorCode.INVALID_INPUT, details=details)


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(
        exc.code, task_id=exc.task_id, details=exc.details, retry_after_seconds=exc.retry_after_seconds
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    # 框架层错误统一为登记表中的错误体；路径或方法不存在都视为资源不存在，不暴露路由结构
    if exc.status_code in (404, 405):
        return error_response(ErrorCode.NOT_FOUND)
    if exc.status_code < 500:
        return error_response(
            ErrorCode.INVALID_INPUT, details=[ErrorDetail(code="http_error", message=str(exc.detail))]
        )
    return error_response(ErrorCode.INTERNAL_ERROR)


def install_error_handling(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_middleware(RequestContextMiddleware)
