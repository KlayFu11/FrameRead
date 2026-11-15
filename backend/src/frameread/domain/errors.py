import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class ErrorAction(StrEnum):
    FIX_INPUT = "fix_input"
    RESOLVE_SAME_KEY = "resolve_same_key"
    RETRY_LATER = "retry_later"
    LOGIN = "login"
    REFRESH = "refresh"
    RETRY_LATER_OR_REPORT = "retry_later_or_report"
    NONE = "none"


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_VIDEO = "UNSUPPORTED_VIDEO"
    INVALID_ANCHOR = "INVALID_ANCHOR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONVERSATION_BUSY = "CONVERSATION_BUSY"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    CURSOR_RESET_REQUIRED = "CURSOR_RESET_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    QUEUE_FULL = "QUEUE_FULL"
    ADMISSION_UNCONFIRMED = "ADMISSION_UNCONFIRMED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    MAINTENANCE = "MAINTENANCE"
    ADMIN_REQUIRED = "ADMIN_REQUIRED"
    CSRF_REJECTED = "CSRF_REJECTED"
    ORIGIN_REJECTED = "ORIGIN_REJECTED"
    NOT_FOUND = "NOT_FOUND"
    SHARE_NOT_AVAILABLE = "SHARE_NOT_AVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # 任务错误码：只出现在 TaskSnapshot.error.code，不作为 HTTP 状态（SPEC §4.1）
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    DISPATCH_EXHAUSTED = "DISPATCH_EXHAUSTED"
    PIPELINE_NOT_AVAILABLE = "PIPELINE_NOT_AVAILABLE"


@dataclass(frozen=True)
class ErrorSpec:
    http_status: int | None
    action: ErrorAction
    message: str


_A = ErrorAction
DEFAULT_RETRY_AFTER_SECONDS = 2

ERROR_REGISTRY: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_INPUT: ErrorSpec(422, _A.FIX_INPUT, "输入不符合要求，请修正后重试"),
    ErrorCode.UNSUPPORTED_VIDEO: ErrorSpec(422, _A.FIX_INPUT, "暂不支持该视频链接"),
    ErrorCode.INVALID_ANCHOR: ErrorSpec(422, _A.FIX_INPUT, "选取的片段或画面无效"),
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorSpec(409, _A.REFRESH, "同一操作标识已用于不同的请求内容"),
    ErrorCode.CONVERSATION_BUSY: ErrorSpec(409, _A.RETRY_LATER, "上一轮问答仍在处理"),
    ErrorCode.VERSION_CONFLICT: ErrorSpec(409, _A.REFRESH, "数据已被修改，请刷新后重试"),
    ErrorCode.INVALID_TRANSITION: ErrorSpec(409, _A.REFRESH, "当前状态不允许该操作"),
    ErrorCode.CURSOR_RESET_REQUIRED: ErrorSpec(409, _A.REFRESH, "状态同步需要重新获取快照"),
    ErrorCode.RATE_LIMITED: ErrorSpec(429, _A.RETRY_LATER, "请求过于频繁，请稍后重试"),
    ErrorCode.QUEUE_FULL: ErrorSpec(503, _A.RETRY_LATER, "当前排队已满，本次请求未受理"),
    ErrorCode.ADMISSION_UNCONFIRMED: ErrorSpec(503, _A.RESOLVE_SAME_KEY, "受理结果尚未确认，请使用原操作标识找回"),
    ErrorCode.DEPENDENCY_UNAVAILABLE: ErrorSpec(503, _A.RETRY_LATER, "依赖服务暂不可用"),
    ErrorCode.MAINTENANCE: ErrorSpec(503, _A.RETRY_LATER, "实例正在维护，暂不接受该操作"),
    ErrorCode.ADMIN_REQUIRED: ErrorSpec(401, _A.LOGIN, "需要管理员登录"),
    ErrorCode.CSRF_REJECTED: ErrorSpec(403, _A.REFRESH, "请求校验失败，请刷新页面"),
    ErrorCode.ORIGIN_REJECTED: ErrorSpec(403, _A.NONE, "来源校验失败，请从管理入口地址访问"),
    ErrorCode.NOT_FOUND: ErrorSpec(404, _A.NONE, "资源不存在"),
    ErrorCode.SHARE_NOT_AVAILABLE: ErrorSpec(404, _A.NONE, "分享不可访问"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, _A.RETRY_LATER_OR_REPORT, "服务内部错误，请稍后重试或凭请求标识反馈"),
    ErrorCode.DEADLINE_EXCEEDED: ErrorSpec(None, _A.NONE, "任务超过总期限"),
    ErrorCode.DISPATCH_EXHAUSTED: ErrorSpec(None, _A.NONE, "任务投递重试已耗尽"),
    ErrorCode.PIPELINE_NOT_AVAILABLE: ErrorSpec(None, _A.NONE, "S0 骨架流水线不会生成文章"),
}


@dataclass(frozen=True)
class ErrorDetail:
    code: str
    message: str
    field: str | None = None


@dataclass
class AppError(Exception):
    code: ErrorCode
    task_id: uuid.UUID | None = None
    details: list[ErrorDetail] = field(default_factory=list)
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if ERROR_REGISTRY[self.code].http_status is None:
            raise ValueError(f"{self.code} 是任务错误码，不能作为 HTTP 错误")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 1:
            raise ValueError("retry_after_seconds 必须为正整数")
