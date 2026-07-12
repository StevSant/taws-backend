"""Unit test for `Container.get_tts_provider` DI binding.

Mirrors the graceful-degradation-to-`None` shape of `get_notification_channel`: TTS is
only wired when it's both enabled AND keyed, otherwise the container returns `None`
(the frontend then falls back to browser speech). When wired, the adapter is cached as
a process-wide singleton like every other `get_*` in the container.
"""

from app.core.config import Settings
from app.core.di import Container
from app.infrastructure.tts import OpenAITTSProvider


def test_returns_none_when_tts_disabled() -> None:
    settings = Settings(tts_enabled=False, tts_api_key="sk-tts")
    container = Container(settings=settings)

    assert container.get_tts_provider() is None


def test_returns_none_when_enabled_but_no_key() -> None:
    settings = Settings(tts_enabled=True, tts_api_key=None)
    container = Container(settings=settings)

    assert container.get_tts_provider() is None


def test_returns_openai_adapter_when_enabled_and_keyed() -> None:
    settings = Settings(tts_enabled=True, tts_api_key="sk-tts")
    container = Container(settings=settings)

    provider = container.get_tts_provider()

    assert isinstance(provider, OpenAITTSProvider)


def test_caches_same_instance_across_calls() -> None:
    settings = Settings(tts_enabled=True, tts_api_key="sk-tts")
    container = Container(settings=settings)

    first = container.get_tts_provider()
    second = container.get_tts_provider()

    assert first is second
