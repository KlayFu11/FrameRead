import sys
import traceback
from typing import TextIO

import structlog
from structlog.typing import EventDict, WrappedLogger

# SPEC §20 字段 allowlist；commit_outcome 来自 SPEC §4.1；stack 仅由本模块的脱敏栈处理器写入
ALLOWED_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "event",
        "request_id",
        "task_id",
        "attempt_id",
        "fence",
        "stage",
        "provider_call_id",
        "article_version_id",
        "worker_id",
        "epoch",
        "error_code",
        "duration_ms",
        "queue_wait_ms",
        "resource_wait_ms",
        "usage_status",
        "commit_outcome",
    }
)
_STACK_FIELD = "stack"


class LogFieldNotAllowed(Exception):
    pass


def _enforce_allowlist(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    extra = set(event_dict) - ALLOWED_FIELDS - {"exc_info"}
    if extra:
        raise LogFieldNotAllowed(f"日志字段不在 allowlist 中: {sorted(extra)}")
    return event_dict


def _sanitized_stack(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """只保留异常类型与帧位置，丢弃异常消息（可能含 SQL、URL 或用户内容）。"""
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict
    if exc_info is True:
        exc_info = sys.exc_info()
    exc_type, _exc, tb = exc_info
    if exc_type is None:
        return event_dict
    frames = [f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)]
    event_dict[_STACK_FIELD] = "\n".join([*frames, exc_type.__name__])
    return event_dict


def configure_logging(stream: TextIO = sys.stdout) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _enforce_allowlist,
            _sanitized_stack,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(stream),
        cache_logger_on_first_use=False,
    )
