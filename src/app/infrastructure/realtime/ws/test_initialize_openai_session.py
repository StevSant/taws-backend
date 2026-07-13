"""Tests for `initialize_openai_session` — the post-connect handshake with OpenAI.

After the OpenAI socket connects, the proxy waits for `session.created`, then sends the
server-authored `session.update`. Driven with a fake socket (no network).
"""

import json
from typing import Any

import pytest

from app.core.config import Settings
from app.infrastructure.realtime.ws.initialize_openai_session import (
    initialize_openai_session,
)


class FakeOpenAISocket:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = [json.dumps(e) for e in events]
        self.sent: list[dict[str, Any]] = []

    def __aiter__(self) -> "FakeOpenAISocket":
        return self

    async def __anext__(self) -> str:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))


@pytest.mark.asyncio
async def test_sends_session_update_after_session_created() -> None:
    socket = FakeOpenAISocket(events=[{"type": "session.created"}])

    await initialize_openai_session(socket, Settings(openai_realtime_voice="alloy"), "es")

    assert len(socket.sent) == 1
    assert socket.sent[0]["type"] == "session.update"
    assert socket.sent[0]["session"]["input_audio_format"] == "pcm16"


@pytest.mark.asyncio
async def test_skips_leading_events_until_session_created() -> None:
    socket = FakeOpenAISocket(events=[{"type": "response.created"}, {"type": "session.created"}])

    await initialize_openai_session(socket, Settings(), "es")

    assert [m["type"] for m in socket.sent] == ["session.update"]


@pytest.mark.asyncio
async def test_stream_ending_before_session_created_sends_nothing() -> None:
    socket = FakeOpenAISocket(events=[{"type": "response.created"}])

    await initialize_openai_session(socket, Settings(), "es")

    assert socket.sent == []
