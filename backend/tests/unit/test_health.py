import asyncio

import pytest

from frameread.observability.health import HealthRegistry, ProbeFailed, Severity


async def ok() -> None:
    return None


async def down() -> None:
    raise ProbeFailed("connection_failed")


async def broken() -> None:
    raise RuntimeError("bug in probe")


async def slow() -> None:
    await asyncio.sleep(5)


def registry(**probes):
    reg = HealthRegistry(timeout_seconds=0.2, cache_seconds=0)
    for name, (fn, severity) in probes.items():
        reg.register_probe(name, fn, severity)
    return reg


async def test_all_ok_is_ready():
    report = await registry(pg=(ok, Severity.CRITICAL), redis=(ok, Severity.DEGRADED)).report()
    assert report.status == "ready"
    assert {c.name: c.status for c in report.checks} == {"pg": "ready", "redis": "ready"}
    assert all(c.observed_at is not None for c in report.checks)


async def test_degraded_dependency_down():
    report = await registry(pg=(ok, Severity.CRITICAL), redis=(down, Severity.DEGRADED)).report()
    assert report.status == "degraded"
    redis = next(c for c in report.checks if c.name == "redis")
    assert redis.status == "degraded" and redis.detail == "connection_failed"


async def test_critical_down_is_unavailable_even_if_other_unknown():
    report = await registry(pg=(down, Severity.CRITICAL), head=(broken, Severity.CRITICAL)).report()
    assert report.status == "unavailable"


@pytest.mark.parametrize("fn", [broken, slow])
async def test_collection_failure_is_unknown_with_null_observation(fn):
    report = await registry(pg=(fn, Severity.CRITICAL)).report()
    (check,) = report.checks
    assert check.status == "unknown" and check.observed_at is None
    assert report.status == "unknown"


async def test_degraded_probe_unknown_degrades_overall():
    report = await registry(pg=(ok, Severity.CRITICAL), redis=(slow, Severity.DEGRADED)).report()
    assert report.status == "degraded"


async def test_results_cached_within_window():
    calls = 0

    async def counting() -> None:
        nonlocal calls
        calls += 1

    reg = HealthRegistry(timeout_seconds=1, cache_seconds=60)
    reg.register_probe("pg", counting, Severity.CRITICAL)
    await reg.report()
    await reg.report()
    assert calls == 1


def test_duplicate_probe_name_rejected():
    reg = HealthRegistry()
    reg.register_probe("pg", ok, Severity.CRITICAL)
    with pytest.raises(ValueError):
        reg.register_probe("pg", ok, Severity.CRITICAL)
