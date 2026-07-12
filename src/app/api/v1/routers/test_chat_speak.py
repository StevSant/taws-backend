"""Endpoint test for `POST /api/v1/chat/speak` (TTS voice playback).

Drives the real route via `TestClient` with DI overrides, covering the three wire
contracts the frontend relies on:
- provider configured -> 200 + `audio/mpeg` + non-empty body
- provider `None` (TTS unconfigured) -> 503, so the client falls back to browser speech
- no/invalid JWT once Supabase Auth is configured -> 401
"""

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_tts_provider, require_current_user
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings
from app.domain.agents.ports import TTSProvider
from app.main import app

_USER_ID = "dev-user"


class _FakeTTSProvider(TTSProvider):
    """Echoes a fixed audio buffer; records the args it was called with."""

    def __init__(self, audio: bytes) -> None:
        self._audio = audio
        self.calls: list[tuple[str, str, str]] = []

    async def synthesize(self, text: str, voice: str, response_format: str) -> bytes:
        self.calls.append((text, voice, response_format))
        return self._audio

    async def synthesize_stream(
        self, text: str, voice: str, response_format: str
    ) -> AsyncIterator[bytes]:
        yield self._audio


def _override_user() -> None:
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )


def test_speak_returns_audio_mpeg_when_provider_configured() -> None:
    provider = _FakeTTSProvider(audio=b"ID3-audio-bytes")
    _override_user()
    app.dependency_overrides[get_tts_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/speak", json={"text": "hello there"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3-audio-bytes"
    # Default voice/format come from Settings (nova/mp3), not hardcoded in the router.
    assert provider.calls == [("hello there", "nova", "mp3")]


def test_speak_uses_requested_voice_when_provided() -> None:
    provider = _FakeTTSProvider(audio=b"audio")
    _override_user()
    app.dependency_overrides[get_tts_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/speak", json={"text": "hi", "voice": "shimmer"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert provider.calls == [("hi", "shimmer", "mp3")]


def test_speak_returns_503_when_provider_unconfigured() -> None:
    _override_user()
    app.dependency_overrides[get_tts_provider] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/speak", json={"text": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_speak_returns_401_without_jwt_when_auth_configured() -> None:
    # Configure SUPABASE_URL so `require_current_user` enforces auth (its dev fallback
    # only applies when SUPABASE_URL is unset). No Authorization header is sent.
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_url="https://example.supabase.co"
    )
    app.dependency_overrides[get_tts_provider] = lambda: _FakeTTSProvider(audio=b"x")
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/speak", json={"text": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_speak_rejects_empty_text() -> None:
    # Empty text is always invalid regardless of config — never bill the TTS provider for it.
    provider = _FakeTTSProvider(audio=b"x")
    _override_user()
    app.dependency_overrides[get_tts_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/speak", json={"text": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert provider.calls == []  # never synthesized -> no cost


def test_speak_rejects_text_over_configured_max() -> None:
    # Over the Settings-driven char cap -> reject before hitting the billed TTS API.
    provider = _FakeTTSProvider(audio=b"x")
    _override_user()
    app.dependency_overrides[get_settings] = lambda: Settings(tts_max_input_chars=5)
    app.dependency_overrides[get_tts_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/speak", json={"text": "way too long"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert provider.calls == []  # rejected before synthesis -> no OpenAI cost
