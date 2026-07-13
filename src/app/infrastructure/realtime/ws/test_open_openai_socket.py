"""Tests for the pure parts of the OpenAI socket seam: key resolution + URL building.

The actual `connect()` needs a live OpenAI key + reachable endpoint, so only the pure
helpers are unit-tested here.
"""

from app.core.config import Settings
from app.infrastructure.realtime.ws.open_openai_socket import (
    build_openai_realtime_url,
    resolve_realtime_api_key,
)


def test_prefers_dedicated_realtime_key() -> None:
    settings = Settings(openai_realtime_api_key="rt-key", openai_api_key="chat-key")
    assert resolve_realtime_api_key(settings) == "rt-key"


def test_falls_back_to_openai_api_key() -> None:
    settings = Settings(openai_realtime_api_key=None, openai_api_key="chat-key")
    assert resolve_realtime_api_key(settings) == "chat-key"


def test_none_when_no_key_configured() -> None:
    settings = Settings(openai_realtime_api_key=None, openai_api_key=None)
    assert resolve_realtime_api_key(settings) is None


def test_url_carries_model_as_query_param() -> None:
    url = build_openai_realtime_url("gpt-realtime-2.1-mini")
    assert url == "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini"
