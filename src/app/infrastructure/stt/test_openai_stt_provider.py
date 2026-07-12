"""Unit test for the `OpenAISTTProvider` adapter.

Mirror image of `test_openai_tts_provider`: pass-through of model + the multipart
`file=(filename, bytes, content_type)` tuple to the SDK and a missing-key path that
degrades to `""` WITHOUT any network call. `AsyncOpenAI` is patched so no real HTTP
happens.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.stt import OpenAISTTProvider

_MODULE = "app.infrastructure.stt.openai_stt_provider"


def _mock_client_returning(text: str) -> MagicMock:
    """Build a MagicMock shaped like `AsyncOpenAI`, whose
    `audio.transcriptions.create(...)` awaits to a response exposing `.text`.
    """
    transcription = MagicMock()
    transcription.text = text
    client = MagicMock()
    client.audio.transcriptions.create = AsyncMock(return_value=transcription)
    return client


async def test_transcribe_passes_model_and_file_tuple_and_returns_text() -> None:
    client = _mock_client_returning("hola mundo")
    with patch(f"{_MODULE}.AsyncOpenAI", return_value=client) as async_openai:
        provider = OpenAISTTProvider(api_key="sk-test", model="whisper-1")

        text = await provider.transcribe(b"RIFF-audio", "clip.wav", "audio/wav")

    async_openai.assert_called_once_with(api_key="sk-test")
    client.audio.transcriptions.create.assert_awaited_once_with(
        model="whisper-1", file=("clip.wav", b"RIFF-audio", "audio/wav")
    )
    assert text == "hola mundo"


async def test_missing_key_transcribe_degrades_without_network_call() -> None:
    with patch(f"{_MODULE}.AsyncOpenAI") as async_openai:
        provider = OpenAISTTProvider(api_key=None, model="whisper-1")

        text = await provider.transcribe(b"RIFF-audio", "clip.wav", "audio/wav")

    # No client constructed, so no possible network call.
    async_openai.assert_not_called()
    assert text == ""
