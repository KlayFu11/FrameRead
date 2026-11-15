import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

import structlog

ProbeFn = Callable[[], Awaitable[None]]
CheckStatus = Literal["ready", "degraded", "unavailable", "unknown"]
_log = structlog.get_logger()


class Severity(StrEnum):
    CRITICAL = "critical"
    DEGRADED = "degraded"


class ProbeFailed(Exception):
    """探针已确认依赖不可用；detail 为不含敏感信息的短代码。"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Check:
    name: str
    status: CheckStatus
    observed_at: datetime | None
    detail: str | None = None


@dataclass(frozen=True)
class HealthReport:
    status: CheckStatus
    checks: list[Check]

    @property
    def http_status(self) -> int:
        return 200 if self.status in ("ready", "degraded") else 503


@dataclass
class _Probe:
    fn: ProbeFn
    severity: Severity
    cached: Check | None = None
    cached_at: float = 0.0


class HealthRegistry:
    """各模块注册依赖探针，M01 聚合；超时 2s、缓存 5s（D13）。"""

    def __init__(self, *, timeout_seconds: float = 2.0, cache_seconds: float = 5.0) -> None:
        self._timeout = timeout_seconds
        self._cache = cache_seconds
        self._probes: dict[str, _Probe] = {}

    def register_probe(self, name: str, fn: ProbeFn, severity: Severity) -> None:
        if name in self._probes:
            raise ValueError(f"探针 {name} 已注册")
        self._probes[name] = _Probe(fn, severity)

    async def _run(self, name: str, probe: _Probe) -> Check:
        now = time.monotonic()
        if probe.cached is not None and now - probe.cached_at < self._cache:
            return probe.cached
        failed: CheckStatus = "unavailable" if probe.severity is Severity.CRITICAL else "degraded"
        try:
            await asyncio.wait_for(probe.fn(), self._timeout)
            check = Check(name, "ready", datetime.now(UTC))
        except ProbeFailed as exc:
            check = Check(name, failed, datetime.now(UTC), exc.detail)
        except Exception:
            # 采集失败不能当作健康或 0，状态 unknown 且无观测时间
            _log.exception(f"health_probe_unknown.{name}", error_code="INTERNAL_ERROR")
            check = Check(name, "unknown", None)
        probe.cached, probe.cached_at = check, now
        return check

    async def report(self) -> HealthReport:
        checks = list(await asyncio.gather(*(self._run(n, p) for n, p in self._probes.items())))
        critical = [c for c in checks if self._probes[c.name].severity is Severity.CRITICAL]
        if any(c.status == "unavailable" for c in critical):
            status: CheckStatus = "unavailable"
        elif any(c.status == "unknown" for c in critical):
            status = "unknown"
        elif any(c.status != "ready" for c in checks):
            status = "degraded"
        else:
            status = "ready"
        return HealthReport(status, checks)
