from collections.abc import AsyncIterator
from typing import Literal, cast

from openai import AsyncOpenAI

from app.domain.agents.ports import TTSProvider

# The SDK types `response_format` as this closed `Literal`; the port deals in plain
# `str` to stay vendor-neutral, so we adapt at this boundary (same `cast`-at-the-edge
# pattern as `OpenAIProvider`). Allowed values match `Settings.tts_response_format`.
_ResponseFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]

# Default byte size each `synthesize_stream` chunk is sliced to. Buffered synthesis is
# the only real streaming shape OpenAI TTS supports (no stream-to-service), so this
# just paces delivery of an already-complete buffer to the caller.
_DEFAULT_CHUNK_SIZE = 4096


class OpenAITTSProvider(TTSProvider):
    """`TTSProvider` adapter backed by the OpenAI Audio Speech API.

    Guarded so the app never crashes when no TTS key is configured: `synthesize()`
    returns empty audio and `synthesize_stream()` yields nothing in that case, WITHOUT
    ever constructing a client or hitting the network — the same missing-key guard
    shape as `OpenAIProvider`. `voice`/`response_format` are passed straight through
    from the caller (the DI-wired `Settings` values), never hardcoded here.
    """

    def __init__(
        self, api_key: str | None, model: str, chunk_size: int = _DEFAULT_CHUNK_SIZE
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model
        self._chunk_size = chunk_size

    async def synthesize(self, text: str, voice: str, response_format: str) -> bytes:
        if self._client is None:
            return b""

        response = await self._client.audio.speech.create(
            model=self._model,
            voice=voice,
            response_format=cast(_ResponseFormat, response_format),
            input=text,
        )
        return response.content

    async def synthesize_stream(
        self, text: str, voice: str, response_format: str
    ) -> AsyncIterator[bytes]:
        audio = await self.synthesize(text, voice, response_format)
        for start in range(0, len(audio), self._chunk_size):
            yield audio[start : start + self._chunk_size]
