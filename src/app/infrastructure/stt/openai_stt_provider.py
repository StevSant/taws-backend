from openai import AsyncOpenAI

from app.domain.agents.ports import STTProvider


class OpenAISTTProvider(STTProvider):
    """`STTProvider` adapter backed by the OpenAI Audio Transcriptions API (Whisper).

    The mirror image of `OpenAITTSProvider`. Guarded so the app never crashes when no
    STT key is configured: `transcribe()` returns an empty string in that case, WITHOUT
    ever constructing a client or hitting the network — the same missing-key guard shape
    as `OpenAIProvider`/`OpenAITTSProvider`. `model` is passed straight through from the
    DI-wired `Settings` value, never hardcoded here.
    """

    def __init__(self, api_key: str | None, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        if self._client is None:
            return ""

        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=(filename, audio, content_type),
        )
        return response.text
