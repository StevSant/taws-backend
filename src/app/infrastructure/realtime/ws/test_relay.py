"""Lifecycle tests for `run_realtime_relay` — the two-way audio relay coordinator.

Driven entirely with in-memory fake sockets (no OpenAI, no browser, no mic):
- the browser side mimics FastAPI's `WebSocket` (`receive_json`/`send_json`/`close`),
  raising `WebSocketDisconnect` when its scripted messages run out;
- the OpenAI side mimics a `websockets` client (async-iterable of JSON strings, `send`,
  `close`), stopping iteration when its scripted events run out.

The relay must: forward browser audio as `input_audio_buffer.append`, map OpenAI events
to browser messages, intercept a `response.done` function_call and dispatch it in-process
with the JWT user id, and — on either side ending — cancel both pumps and close BOTH
sockets (no leaked OpenAI socket).
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.infrastructure.realtime.ws import relay as relay_module
from app.infrastructure.realtime.ws.relay import run_realtime_relay


class FakeBrowserSocket:
    """Mimics the subset of FastAPI `WebSocket` the relay uses."""

    def __init__(self, incoming: list[dict[str, Any]]) -> None:
        self._incoming = list(incoming)
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def receive_json(self) -> dict[str, Any]:
        if not self._incoming:
            raise WebSocketDisconnect(code=1000)
        return self._incoming.pop(0)

    async def send_json(self, data: Any, mode: str = "text") -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


class FakeOpenAISocket:
    """Mimics the subset of a `websockets` client the relay uses."""

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


def _settings() -> Settings:
    return Settings(openai_realtime_ttl_seconds=600)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="jwt-user-1")


def _container() -> Any:
    return SimpleNamespace(_settings=SimpleNamespace(default_locale="en"))


@pytest.mark.asyncio
async def test_browser_disconnect_closes_both_sockets() -> None:
    browser = FakeBrowserSocket(incoming=[])  # immediate disconnect
    openai = FakeOpenAISocket(events=[{"type": "response.output_audio.delta", "delta": "x"}])

    await run_realtime_relay(browser, openai, _container(), _user(), _settings())

    assert openai.closed is True
    assert browser.closed is True


@pytest.mark.asyncio
async def test_openai_stream_end_closes_both_sockets() -> None:
    # Browser keeps "listening" (no messages, but not disconnected until openai ends first).
    browser = FakeBrowserSocket(incoming=[{"type": "audio", "data": "QQ=="}])
    openai = FakeOpenAISocket(events=[])  # OpenAI stream ends immediately

    await run_realtime_relay(browser, openai, _container(), _user(), _settings())

    assert openai.closed is True
    assert browser.closed is True


@pytest.mark.asyncio
async def test_browser_audio_forwarded_as_input_audio_buffer_append() -> None:
    browser = FakeBrowserSocket(incoming=[{"type": "audio", "data": "QUJD"}])
    openai = FakeOpenAISocket(events=[])

    await run_realtime_relay(browser, openai, _container(), _user(), _settings())

    appends = [m for m in openai.sent if m.get("type") == "input_audio_buffer.append"]
    assert appends and appends[0]["audio"] == "QUJD"


@pytest.mark.asyncio
async def test_openai_audio_delta_mapped_to_browser() -> None:
    browser = FakeBrowserSocket(incoming=[])
    openai = FakeOpenAISocket(events=[{"type": "response.output_audio.delta", "delta": "QUJD"}])

    await run_realtime_relay(browser, openai, _container(), _user(), _settings())

    audio = [m for m in browser.sent if m.get("type") == "audio"]
    assert audio and audio[0]["data"] == "QUJD"


@pytest.mark.asyncio
async def test_function_call_dispatched_in_process_with_jwt_user_id() -> None:
    from app.domain.signals.entities import ImpactClass, Signal

    signal = Signal(
        id="sig-1",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.7,
        evidence=[],
        disclaimer="not advice",
        thesis="Bullish.",
    )
    use_case = Mock()
    use_case.execute = AsyncMock(return_value=signal)
    container = SimpleNamespace(
        _settings=SimpleNamespace(default_locale="en"),
        get_generate_signal_use_case=Mock(return_value=use_case),
    )

    done_event = {
        "type": "response.done",
        "response": {
            "output": [
                {
                    "type": "function_call",
                    "name": "generate_signal",
                    "call_id": "call-9",
                    "arguments": json.dumps({"symbol": "aapl"}),
                }
            ]
        },
    }
    browser = FakeBrowserSocket(incoming=[])
    openai = FakeOpenAISocket(events=[done_event])

    await run_realtime_relay(browser, openai, container, _user(), _settings())

    # The tool ran in-process with the JWT user id (never a client value).
    use_case.execute.assert_awaited_once_with("AAPL", "en")
    # Its output + a response.create were sent back to OpenAI.
    sent_types = [m.get("type") for m in openai.sent]
    assert "conversation.item.create" in sent_types
    assert "response.create" in sent_types
    # The browser saw tool-call lifecycle notifications.
    browser_types = [m.get("type") for m in browser.sent]
    assert "tool-call-started" in browser_types
    assert "tool-call-finished" in browser_types


class HangingBrowserSocket:
    """A browser socket whose pump blocks forever until cancelled by the duration cap."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.receive_cancelled = False

    async def receive_json(self) -> dict[str, Any]:
        try:
            await asyncio.Event().wait()  # never resolves
        except asyncio.CancelledError:
            self.receive_cancelled = True
            raise
        raise WebSocketDisconnect(code=1000)  # pragma: no cover

    async def send_json(self, data: Any, mode: str = "text") -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = True


class HangingOpenAISocket:
    """An OpenAI socket whose iterator blocks forever until cancelled by the duration cap."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.iter_cancelled = False

    def __aiter__(self) -> "HangingOpenAISocket":
        return self

    async def __anext__(self) -> str:
        try:
            await asyncio.Event().wait()  # never yields an event
        except asyncio.CancelledError:
            self.iter_cancelled = True
            raise
        raise StopAsyncIteration  # pragma: no cover

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_duration_cap_cancels_pumps_and_closes_both_sockets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Both sides hang forever; only the max-duration cap can end the session. When it
    # elapses, BOTH pump tasks must be cancelled and BOTH sockets closed deterministically.
    # The absolute cap is patched to a tiny float so the test doesn't wait real seconds; it
    # is small but positive, so both pumps actually start (and reach their blocking await)
    # before the cap fires — exactly the leaked-task scenario the fix must handle.
    monkeypatch.setattr(relay_module, "_MAX_SESSION_SECONDS_CAP", 0.05)
    browser = HangingBrowserSocket()
    openai = HangingOpenAISocket()

    await asyncio.wait_for(
        run_realtime_relay(browser, openai, _container(), _user(), _settings()),
        timeout=5,  # test-level guard: if the cap fails to fire, fail fast instead of hanging
    )

    assert browser.receive_cancelled is True
    assert openai.iter_cancelled is True
    assert openai.closed is True
    assert browser.closed is True


class MalformedThenGoodBrowserSocket(FakeBrowserSocket):
    """First `receive_json` raises like a non-JSON text frame; then it yields real messages."""

    def __init__(self, incoming: list[dict[str, Any]]) -> None:
        super().__init__(incoming)
        self._raised_once = False

    async def receive_json(self) -> dict[str, Any]:
        if not self._raised_once:
            self._raised_once = True
            raise json.JSONDecodeError("bad frame", "<<not json>>", 0)
        return await super().receive_json()


@pytest.mark.asyncio
async def test_malformed_browser_message_is_skipped_and_session_continues() -> None:
    # A malformed (non-JSON) browser frame must NOT kill the session: it is skipped and the
    # next good message is still forwarded to OpenAI.
    browser = MalformedThenGoodBrowserSocket(incoming=[{"type": "audio", "data": "QUJD"}])
    openai = FakeOpenAISocket(events=[])

    await run_realtime_relay(browser, openai, _container(), _user(), _settings())

    appends = [m for m in openai.sent if m.get("type") == "input_audio_buffer.append"]
    assert appends and appends[0]["audio"] == "QUJD"
    assert openai.closed is True
    assert browser.closed is True
