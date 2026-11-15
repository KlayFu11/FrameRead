import io

import httpx
import structlog
from fastapi import FastAPI

from frameread.api.errors import install_error_handling
from frameread.observability.logging import configure_logging


async def test_failed_request_logs_request_id_but_not_body_or_url():
    buf = io.StringIO()
    configure_logging(buf)
    app = FastAPI()
    install_error_handling(app)

    @app.post("/boom")
    async def boom() -> None:
        raise RuntimeError("explode")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/boom?token=SECRET-QUERY", json={"password": "SECRET-BODY"})
    finally:
        structlog.reset_defaults()
    logged = buf.getvalue()
    assert resp.status_code == 500
    assert resp.headers["X-Request-ID"] in logged
    assert "SECRET-QUERY" not in logged and "SECRET-BODY" not in logged and "explode" not in logged
