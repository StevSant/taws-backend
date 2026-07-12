"""Endpoint test for `POST /api/v1/chat/transcribe` (voice dictation -> text).

Mirror image of `test_chat_speak`: drives the real route via `TestClient` with DI
overrides and a multipart file upload, covering the wire contracts the frontend relies
on:
- provider configured -> 200 + `{"text": ...}`
- provider `None` (STT unconfigured) -> 503, so the client falls back to browser speech
  recognition
- audio over the Settings-driven byte cap -> 422 BEFORE the billed API is hit
- empty audio -> 422 (never billed)
- no/invalid JWT once Supabase Auth is configured -> 401
"""

from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_stt_provider, require_current_user
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings
from app.domain.agents.ports import STTProvider
from app.main import app

_USER_ID = "dev-user"


class _FakeSTTProvider(STTProvider):
    """Echoes a fixed transcript; records the args it was called with."""

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        self.calls.append((audio, filename, content_type))
        return self._transcript


def _override_user() -> None:
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )


def test_transcribe_returns_text_when_provider_configured() -> None:
    provider = _FakeSTTProvider(transcript="hello there")
    _override_user()
    app.dependency_overrides[get_stt_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/transcribe",
                files={"file": ("clip.wav", b"RIFF-audio-bytes", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"text": "hello there"}
    assert provider.calls == [(b"RIFF-audio-bytes", "clip.wav", "audio/wav")]


def test_transcribe_returns_503_when_provider_unconfigured() -> None:
    _override_user()
    app.dependency_overrides[get_stt_provider] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/transcribe",
                files={"file": ("clip.wav", b"audio", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_transcribe_rejects_audio_over_configured_max() -> None:
    # Over the Settings-driven byte cap -> reject before hitting the billed STT API.
    provider = _FakeSTTProvider(transcript="x")
    _override_user()
    app.dependency_overrides[get_settings] = lambda: Settings(stt_max_audio_bytes=4)
    app.dependency_overrides[get_stt_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/transcribe",
                files={"file": ("clip.wav", b"way too many bytes", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert provider.calls == []  # rejected before transcription -> no OpenAI cost


def test_transcribe_rejects_empty_audio() -> None:
    # Empty audio is always invalid regardless of config — never bill the STT provider.
    provider = _FakeSTTProvider(transcript="x")
    _override_user()
    app.dependency_overrides[get_stt_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/transcribe",
                files={"file": ("clip.wav", b"", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert provider.calls == []  # never transcribed -> no cost


def test_transcribe_returns_401_without_jwt_when_auth_configured() -> None:
    # Configure SUPABASE_URL so `require_current_user` enforces auth (its dev fallback
    # only applies when SUPABASE_URL is unset). No Authorization header is sent.
    app.dependency_overrides[get_settings] = lambda: Settings(
        supabase_url="https://example.supabase.co"
    )
    app.dependency_overrides[get_stt_provider] = lambda: _FakeSTTProvider(transcript="x")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/transcribe",
                files={"file": ("clip.wav", b"audio", "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
