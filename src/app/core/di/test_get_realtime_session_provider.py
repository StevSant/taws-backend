"""Gating tests for `Container.get_realtime_session_provider`.

Mirrors `get_tts_provider`/`get_notification_channel`'s "unconfigured -> None" pattern,
with the hackathon-friction twist that the Realtime key falls back to `openai_api_key`
when the dedicated `openai_realtime_api_key` is unset.
"""

from app.core.config import Settings
from app.core.di.container import Container
from app.infrastructure.realtime import OpenAIRealtimeSessionProvider


def _container(**overrides: object) -> Container:
    return Container(settings=Settings(**overrides))  # type: ignore[arg-type]


def test_returns_none_when_disabled_even_with_key() -> None:
    container = _container(openai_realtime_enabled=False, openai_api_key="sk-x")

    assert container.get_realtime_session_provider() is None


def test_returns_none_when_enabled_but_no_key_available() -> None:
    container = _container(
        openai_realtime_enabled=True,
        openai_realtime_api_key=None,
        openai_api_key=None,
    )

    assert container.get_realtime_session_provider() is None


def test_returns_adapter_when_enabled_with_dedicated_key() -> None:
    container = _container(
        openai_realtime_enabled=True, openai_realtime_api_key="sk-realtime"
    )

    provider = container.get_realtime_session_provider()

    assert isinstance(provider, OpenAIRealtimeSessionProvider)


def test_falls_back_to_openai_api_key_when_dedicated_key_unset() -> None:
    container = _container(
        openai_realtime_enabled=True,
        openai_realtime_api_key=None,
        openai_api_key="sk-shared",
    )

    provider = container.get_realtime_session_provider()

    assert isinstance(provider, OpenAIRealtimeSessionProvider)


def test_provider_is_cached_singleton() -> None:
    container = _container(
        openai_realtime_enabled=True, openai_realtime_api_key="sk-realtime"
    )

    first = container.get_realtime_session_provider()
    second = container.get_realtime_session_provider()

    assert first is second
