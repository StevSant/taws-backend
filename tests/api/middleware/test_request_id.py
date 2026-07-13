"""Unit tests for the pure-ASGI `RequestIDMiddleware`.

Drives the middleware directly with hand-built ASGI scope/receive/send (no FastAPI
TestClient) so the raw request-id + timing behavior is exercised in isolation.
"""

import logging
from typing import Any

import pytest

from app.api.middleware import RequestIDMiddleware

_REQUEST_ID_HEADER = b"x-request-id"


class _SendRecorder:
    """Captures every ASGI message the middleware forwards downstream."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": headers or [],
    }


async def _ok_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


def _response_start(recorder: _SendRecorder) -> dict[str, Any]:
    return next(m for m in recorder.messages if m["type"] == "http.response.start")


def _header_value(message: dict[str, Any], name: bytes) -> bytes | None:
    return next((value for key, value in message["headers"] if key.lower() == name), None)


async def test_mints_and_echoes_a_request_id_when_none_is_supplied() -> None:
    recorder = _SendRecorder()
    scope = _http_scope()

    await RequestIDMiddleware(_ok_app)(scope, _receive, recorder)

    echoed = _header_value(_response_start(recorder), _REQUEST_ID_HEADER)
    assert echoed is not None
    assert scope["state"]["request_id"] == echoed.decode()


async def test_reuses_an_inbound_request_id() -> None:
    recorder = _SendRecorder()
    scope = _http_scope(headers=[(_REQUEST_ID_HEADER, b"inbound-123")])

    await RequestIDMiddleware(_ok_app)(scope, _receive, recorder)

    assert _header_value(_response_start(recorder), _REQUEST_ID_HEADER) == b"inbound-123"
    assert scope["state"]["request_id"] == "inbound-123"


async def test_logs_one_timing_line_on_completion(caplog: pytest.LogCaptureFixture) -> None:
    recorder = _SendRecorder()
    with caplog.at_level(logging.INFO, logger="app.api.middleware.request_id"):
        await RequestIDMiddleware(_ok_app)(_http_scope(), _receive, recorder)

    records = [r for r in caplog.records if r.name == "app.api.middleware.request_id"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "status=200" in message
    assert "duration_ms=" in message


async def test_logs_status_500_and_reraises_when_the_app_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _boom(scope: dict[str, Any], receive: Any, send: Any) -> None:
        raise RuntimeError("kaboom")

    recorder = _SendRecorder()
    with (
        caplog.at_level(logging.INFO, logger="app.api.middleware.request_id"),
        pytest.raises(RuntimeError, match="kaboom"),
    ):
        await RequestIDMiddleware(_boom)(_http_scope(), _receive, recorder)

    records = [r for r in caplog.records if r.name == "app.api.middleware.request_id"]
    assert len(records) == 1
    assert "status=500" in records[0].getMessage()


async def test_non_http_scopes_pass_through_untouched() -> None:
    seen: dict[str, Any] = {}

    async def _lifespan_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        seen["scope"] = scope
        seen["send"] = send

    recorder = _SendRecorder()
    await RequestIDMiddleware(_lifespan_app)({"type": "lifespan"}, _receive, recorder)

    # Passed straight through: the inner app received the original send, not a wrapper.
    assert seen["send"] is recorder
    assert seen["scope"]["type"] == "lifespan"
