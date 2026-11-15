import io
import json

import pytest
import structlog

from frameread.observability.logging import LogFieldNotAllowed, configure_logging


@pytest.fixture
def stream():
    buf = io.StringIO()
    configure_logging(buf)
    yield buf
    structlog.reset_defaults()


def lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines()]


def test_allowed_fields_are_written_as_json(stream):
    structlog.get_logger().info("task_claimed", task_id="t1", fence=3, duration_ms=12)
    (rec,) = lines(stream)
    assert rec["event"] == "task_claimed"
    assert rec["task_id"] == "t1" and rec["fence"] == 3
    assert rec["level"] == "info" and "timestamp" in rec


def test_field_outside_allowlist_raises(stream):
    with pytest.raises(LogFieldNotAllowed):
        structlog.get_logger().info("oops", url="https://example.com/?token=abc")
    assert stream.getvalue() == ""


def test_bound_context_fields_are_checked_too(stream):
    with structlog.contextvars.bound_contextvars(session="s"), pytest.raises(LogFieldNotAllowed):
        structlog.get_logger().info("oops")


def test_exception_stack_keeps_frames_but_drops_message(stream):
    def leak() -> None:
        raise ValueError("SELECT * FROM secrets WHERE token='abc'")

    try:
        leak()
    except ValueError:
        structlog.get_logger().exception("unhandled_exception", error_code="INTERNAL_ERROR")
    (rec,) = lines(stream)
    assert "ValueError" in rec["stack"]
    assert "leak" in rec["stack"]
    assert "secrets" not in json.dumps(rec) and "abc" not in json.dumps(rec)
