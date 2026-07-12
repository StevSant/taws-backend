"""Unit test for `Container.get_stt_provider` DI binding.

Mirror image of `test_get_tts_provider`: STT is only wired when it's both enabled AND
keyed, otherwise the container returns `None` (the frontend then falls back to browser
speech recognition). When wired, the adapter is cached as a process-wide singleton like
every other `get_*` in the container.
"""

from app.core.config import Settings
from app.core.di import Container
from app.infrastructure.stt import OpenAISTTProvider


def test_returns_none_when_stt_disabled() -> None:
    settings = Settings(stt_enabled=False, stt_api_key="sk-stt")
    container = Container(settings=settings)

    assert container.get_stt_provider() is None


def test_returns_none_when_enabled_but_no_key() -> None:
    settings = Settings(stt_enabled=True, stt_api_key=None)
    container = Container(settings=settings)

    assert container.get_stt_provider() is None


def test_returns_openai_adapter_when_enabled_and_keyed() -> None:
    settings = Settings(stt_enabled=True, stt_api_key="sk-stt")
    container = Container(settings=settings)

    provider = container.get_stt_provider()

    assert isinstance(provider, OpenAISTTProvider)


def test_caches_same_instance_across_calls() -> None:
    settings = Settings(stt_enabled=True, stt_api_key="sk-stt")
    container = Container(settings=settings)

    first = container.get_stt_provider()
    second = container.get_stt_provider()

    assert first is second
