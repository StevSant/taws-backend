"""Contract test for the `TTSProvider` port.

`TTSProvider` is a pure domain port (ABC) — this proves its abstract contract via a
minimal in-memory `FakeTTSProvider` subclass, the same "prove the port shape with a
fake, no vendor" approach the rest of the domain layer uses. It asserts the two
methods a text-to-speech backend must implement: `synthesize()` returns the full audio
as `bytes`, and `synthesize_stream()` yields the audio as `bytes` chunks.
"""

from collections.abc import AsyncIterator

from app.domain.agents.ports import TTSProvider


class _FakeTTSProvider(TTSProvider):
    """In-memory `TTSProvider` echoing a deterministic audio buffer, no vendor SDK."""

    def __init__(self, audio: bytes) -> None:
        self._audio = audio

    async def synthesize(self, text: str, voice: str, response_format: str) -> bytes:
        return self._audio

    async def synthesize_stream(
        self, text: str, voice: str, response_format: str
    ) -> AsyncIterator[bytes]:
        yield self._audio


async def test_synthesize_returns_bytes() -> None:
    provider = _FakeTTSProvider(audio=b"ID3-audio-bytes")

    audio = await provider.synthesize("hello", voice="nova", response_format="mp3")

    assert isinstance(audio, bytes)
    assert audio == b"ID3-audio-bytes"


async def test_synthesize_stream_yields_bytes() -> None:
    provider = _FakeTTSProvider(audio=b"ID3-audio-bytes")

    chunks = [chunk async for chunk in provider.synthesize_stream("hello", "nova", "mp3")]

    assert chunks == [b"ID3-audio-bytes"]
    assert all(isinstance(chunk, bytes) for chunk in chunks)
