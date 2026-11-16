from typing import Annotated, Literal, Self
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import Field, model_validator

from frameread.api.runtime import require_runtime
from frameread.api.schemas import ErrorEnvelope, StrictModel
from frameread.api.sessions import COOKIE_PATH, require_admin
from frameread.domain.errors import AppError, ErrorCode, ErrorDetail
from frameread.domain.video_input import normalize_video_input, request_digest
from frameread.media.video_url import UnsupportedVideoURL, VideoURLInputError
from frameread.services.admission import AdmissionRequest, TaskAccepted, find_operation, submit_admission
from frameread.services.task_snapshot import TaskSnapshot, read_snapshot

_log = structlog.get_logger()


class VideoTaskCreate(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    mode: Literal["complete", "topic"] = "complete"
    depth: Literal["brief", "standard", "detailed"] = "standard"
    focus: str | None = Field(default=None, max_length=2000)
    provider_config_id: str | None = None
    asr_config_id: str | None = None
    intent: Literal["new", "reinterpret"] = "new"

    @model_validator(mode="after")
    def available_input(self) -> Self:
        details: list[ErrorDetail] = []
        for name in ("provider_config_id", "asr_config_id"):
            if getattr(self, name) is not None:
                details.append(ErrorDetail(field=name, code="config_not_available", message="S0 不支持指定配置"))
        if self.intent != "new":
            details.append(ErrorDetail(field="intent", code="intent_not_available", message="暂不支持重新解读"))
        if self.mode == "topic" and (self.focus is None or not self.focus.strip()):
            details.append(ErrorDetail(field="focus", code="focus_required", message="专题模式需要填写关注点"))
        if details:
            raise AppError(ErrorCode.INVALID_INPUT, details=details)
        return self


def operation_key(raw: str | None) -> UUID:
    try:
        key = UUID(raw) if raw is not None else None
    except ValueError:
        key = None
    if raw is None or key is None or key.version != 4 or str(key) != raw.lower():
        raise AppError(
            ErrorCode.INVALID_INPUT,
            details=[
                ErrorDetail(field="Idempotency-Key", code="uuid4_required", message="操作标识必须为 UUIDv4"),
            ],
        )
    return key


router = APIRouter(
    prefix=COOKIE_PATH,
    tags=["tasks"],
    dependencies=[Depends(require_admin)],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post("/video-tasks", status_code=202, response_model=TaskAccepted)
async def create_video_task(
    body: VideoTaskCreate,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header()],
) -> TaskAccepted:
    key = operation_key(idempotency_key)
    try:
        normalized = normalize_video_input(body.model_dump())
    except UnsupportedVideoURL:
        raise AppError(
            ErrorCode.UNSUPPORTED_VIDEO,
            details=[
                ErrorDetail(field="url", code="unsupported_video", message="暂不支持该视频链接"),
            ],
        ) from None
    except VideoURLInputError:
        raise AppError(
            ErrorCode.INVALID_INPUT,
            details=[
                ErrorDetail(field="url", code="video_url_invalid", message="视频链接格式不正确"),
            ],
        ) from None
    runtime = require_runtime(request)
    accepted = await submit_admission(
        runtime.engine,
        AdmissionRequest(
            key=key,
            request_digest=request_digest(normalized),
            effective_input=normalized,
        ),
    )
    response.headers["Location"] = accepted.snapshot_url
    _log.info("task_accepted", task_id=str(accepted.task_id))
    return accepted


@router.get("/operations/{scope}/{key}", response_model=TaskAccepted)
async def get_operation(scope: Literal["video:new"], key: str, request: Request) -> TaskAccepted:
    return await find_operation(require_runtime(request).engine, scope, operation_key(key))


@router.get("/tasks/{task_id}", response_model=TaskSnapshot)
async def get_task(task_id: UUID, request: Request) -> TaskSnapshot:
    runtime = require_runtime(request)
    if runtime.identity is None:
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE)
    return await read_snapshot(runtime.engine, task_id, runtime.identity.keyring)
