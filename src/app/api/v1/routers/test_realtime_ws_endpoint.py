"""Endpoint tests for the `/api/v1/chat/realtime/ws` WebSocket voice proxy.

Drives the real FastAPI app via `TestClient.websocket_connect`, monkeypatching two seams
in the router module so no OpenAI socket and no real JWKS are needed:
- `verify_realtime_ws_token` -> a canned user (or `None` for the auth-failure case);
- `open_openai_socket` -> an in-memory fake OpenAI socket.

Covers the security-first close codes (1008 invalid token, 1011 unconfigured) and the
happy path (OpenAI socket connected, `session.update` sent, both sockets closed on exit).
"""

import json
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.api.v1.routers.realtime_ws as ws_module
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings
from app.main import app

_USER = CurrentUser(id="jwt-user-1", email="voice@example.com")


class FakeOpenAISocket:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = [json.dumps(e) for e in events]
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    def __aiter__(self) -> "FakeOpenAISocket":
        return self

    async def __anext__(self) -> str:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self) -> None:
        self.closed = True


def _patch_settings_getter(monkeypatch: Any, settings: Settings) -> None:
    # The endpoint calls `get_settings()` directly (not via Depends), so patch the module ref.
    monkeypatch.setattr(ws_module, "get_settings", lambda: settings)
    monkeypatch.setattr(ws_module, "get_container", lambda: SimpleNamespace())


def test_invalid_token_closes_1008(monkeypatch: Any) -> None:
    settings = Settings(openai_realtime_enabled=True, openai_api_key="k")
    _patch_settings_getter(monkeypatch, settings)
    monkeypatch.setattr(ws_module, "verify_realtime_ws_token", lambda _t, _s: None)

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/api/v1/chat/realtime/ws?token=bad") as sock:
                sock.receive_text()
        except WebSocketDisconnect as exc:
            assert exc.code == 1008
        else:  # pragma: no cover - defensive
            raise AssertionError("expected the socket to be closed")


def test_unconfigured_closes_1011(monkeypatch: Any) -> None:
    settings = Settings(openai_realtime_enabled=False)
    _patch_settings_getter(monkeypatch, settings)
    monkeypatch.setattr(ws_module, "verify_realtime_ws_token", lambda _t, _s: _USER)

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/api/v1/chat/realtime/ws?token=t") as sock:
                sock.receive_text()
        except WebSocketDisconnect as exc:
            assert exc.code == 1011
        else:  # pragma: no cover - defensive
            raise AssertionError("expected the socket to be closed")


def test_happy_path_initializes_and_closes_openai_socket(monkeypatch: Any) -> None:
    settings = Settings(
        openai_realtime_enabled=True, openai_api_key="k", openai_realtime_voice="alloy"
    )
    _patch_settings_getter(monkeypatch, settings)
    monkeypatch.setattr(ws_module, "verify_realtime_ws_token", lambda _t, _s: _USER)

    fake_openai = FakeOpenAISocket(events=[{"type": "session.created"}])

    async def _fake_open(_settings: Any, _key: str, _user_id: str) -> FakeOpenAISocket:
        return fake_openai

    monkeypatch.setattr(ws_module, "open_openai_socket", _fake_open)

    with (
        TestClient(app) as client,
        client.websocket_connect("/api/v1/chat/realtime/ws?token=t"),
    ):
        # Connecting + immediately closing the browser side ends the relay.
        pass

    # session.update was sent during the handshake, and the OpenAI socket was closed on exit.
    assert any(m["type"] == "session.update" for m in fake_openai.sent)
    assert fake_openai.closed is True


def test_openai_connect_failure_closes_1013(monkeypatch: Any) -> None:
    settings = Settings(openai_realtime_enabled=True, openai_api_key="k")
    _patch_settings_getter(monkeypatch, settings)
    monkeypatch.setattr(ws_module, "verify_realtime_ws_token", lambda _t, _s: _USER)

    async def _boom(_settings: Any, _key: str, _user_id: str) -> Any:
        raise ConnectionError("openai unreachable")

    monkeypatch.setattr(ws_module, "open_openai_socket", _boom)

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/api/v1/chat/realtime/ws?token=t") as sock:
                sock.receive_text()
        except WebSocketDisconnect as exc:
            assert exc.code == 1013
        else:  # pragma: no cover - defensive
            raise AssertionError("expected the socket to be closed")
