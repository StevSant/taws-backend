"""Contract test for the `STTProvider` port.

Mirrors `test_tts_provider`-style port coverage: a minimal `FakeSTTProvider` proves the
abstract contract — `transcribe(audio, filename, content_type)` awaits to a `str`. Pure
domain: no vendor SDK involved, just the ABC shape callers can depend on.
"""

from app.domain.agents.ports import STTProvider


class _FakeSTTProvider(STTProvider):
    """Returns a fixed transcript; records the args it was called with."""

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        self.calls.append((audio, filename, content_type))
        return self._transcript


async def test_transcribe_returns_str_and_receives_audio_filename_content_type() -> None:
    provider = _FakeSTTProvider(transcript="hello world")

    result = await provider.transcribe(b"RIFF-audio", "clip.wav", "audio/wav")

    assert isinstance(result, str)
    assert result == "hello world"
    assert provider.calls == [(b"RIFF-audio", "clip.wav", "audio/wav")]
