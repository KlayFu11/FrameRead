import uuid

import httpx
import pytest
from fastapi import FastAPI

from frameread.api.errors import install_error_handling
from frameread.api.schemas import StrictModel
from frameread.domain.errors import AppError, ErrorCode


class Body(StrictModel):
    name: str
    count: int


def build_app() -> FastAPI:
    # 测试自建路由触发各类错误；install_error_handling 是生产装配使用的同一入口
    app = FastAPI()
    install_error_handling(app)

    @app.post("/echo")
    async def echo(body: Body) -> dict[str, str]:
        return {"name": body.name}

    @app.post("/conflict")
    async def conflict() -> None:
        raise AppError(ErrorCode.VERSION_CONFLICT, task_id=uuid.UUID(int=7))

    @app.post("/busy")
    async def busy() -> None:
        raise AppError(ErrorCode.QUEUE_FULL)

    @app.post("/boom")
    async def boom() -> None:
        raise RuntimeError("SELECT secret FROM /var/lib/frameread")

    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def assert_request_id(resp: httpx.Response) -> str:
    rid = resp.headers["X-Request-ID"]
    assert uuid.UUID(rid).version == 4
    assert resp.json()["error"]["request_id"] == rid
    return rid


async def test_unknown_field_is_422_invalid_input_with_field_details(client):
    resp = await client.post("/echo", json={"name": "a", "count": "x", "extra": 1})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert err["action"] == "fix_input"
    assert err["retry_after_seconds"] is None
    fields = {d["field"] for d in err["details"]}
    assert fields == {"count", "extra"}
    assert all(set(d) <= {"field", "code", "message"} for d in err["details"])
    assert_request_id(resp)


async def test_app_error_maps_status_action_and_task_id(client):
    resp = await client.post("/conflict")
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "VERSION_CONFLICT"
    assert err["task_id"] == str(uuid.UUID(int=7))
    assert err["retry_after_seconds"] is None
    assert err["details"] == []


async def test_503_carries_retry_after_header_and_field(client):
    resp = await client.post("/busy")
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "QUEUE_FULL"
    assert err["retry_after_seconds"] >= 1
    assert resp.headers["Retry-After"] == str(err["retry_after_seconds"])


async def test_unexpected_exception_is_500_without_leaking_details(client):
    resp = await client.post("/boom")
    assert resp.status_code == 500
    err = resp.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["action"] == "retry_later_or_report"
    assert "secret" not in resp.text and "/var/lib" not in resp.text and "RuntimeError" not in resp.text
    assert_request_id(resp)


async def test_client_supplied_request_id_is_ignored(client):
    supplied = str(uuid.uuid4())
    resp = await client.post("/conflict", headers={"X-Request-ID": supplied})
    assert assert_request_id(resp) != supplied


async def test_unknown_method_is_404_not_found(client):
    resp = await client.get("/echo")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_unknown_path_is_404_not_found(client):
    resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_explicit_retry_after_is_kept_and_429_gets_it_too():
    app = FastAPI()
    install_error_handling(app)

    @app.post("/limited")
    async def limited() -> None:
        raise AppError(ErrorCode.RATE_LIMITED, retry_after_seconds=37)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/limited")
    assert resp.status_code == 429
    assert resp.json()["error"]["retry_after_seconds"] == 37
    assert resp.headers["Retry-After"] == "37"


def test_retry_after_must_be_positive():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        AppError(ErrorCode.QUEUE_FULL, retry_after_seconds=0)


async def test_success_response_also_has_request_id(client):
    resp = await client.post("/echo", json={"name": "a", "count": 1})
    assert resp.status_code == 200
    assert uuid.UUID(resp.headers["X-Request-ID"]).version == 4
