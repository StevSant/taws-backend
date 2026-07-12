"""Unit test for the `OpenAITTSProvider` adapter.

Mirrors the guard/behaviour the OpenAI LLM adapter has: pass-through of
model/voice/response_format to the SDK and a missing-key path that degrades WITHOUT
any network call. `AsyncOpenAI` is patched so no real HTTP happens.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.tts import OpenAITTSProvider

_MODULE = "app.infrastructure.tts.openai_tts_provider"


def _mock_client_returning(audio: bytes) -> MagicMock:
    """Build a MagicMock shaped like `AsyncOpenAI`, whose
    `audio.speech.create(...)` awaits to a binary response exposing `.content`.
    """
    binary_response = MagicMock()
    binary_response.content = audio
    client = MagicMock()
    client.audio.speech.create = AsyncMock(return_value=binary_response)
    return client


async def test_synthesize_passes_model_voice_format_and_returns_bytes() -> None:
    client = _mock_client_returning(b"ID3-audio")
    with patch(f"{_MODULE}.AsyncOpenAI", return_value=client) as async_openai:
        provider = OpenAITTSProvider(api_key="sk-test", model="tts-1")

        audio = await provider.synthesize("hello world", voice="nova", response_format="mp3")

    async_openai.assert_called_once_with(api_key="sk-test")
    client.audio.speech.create.assert_awaited_once_with(
        model="tts-1", voice="nova", response_format="mp3", input="hello world"
    )
    assert audio == b"ID3-audio"


async def test_synthesize_stream_yields_byte_chunks_covering_full_audio() -> None:
    client = _mock_client_returning(b"0123456789")
    with patch(f"{_MODULE}.AsyncOpenAI", return_value=client):
        provider = OpenAITTSProvider(api_key="sk-test", model="tts-1", chunk_size=4)

        chunks = [
            chunk
            async for chunk in provider.synthesize_stream(
                "hello", voice="nova", response_format="mp3"
            )
        ]

    assert all(isinstance(chunk, bytes) for chunk in chunks)
    assert chunks == [b"0123", b"4567", b"89"]
    assert b"".join(chunks) == b"0123456789"


async def test_missing_key_synthesize_degrades_without_network_call() -> None:
    with patch(f"{_MODULE}.AsyncOpenAI") as async_openai:
        provider = OpenAITTSProvider(api_key=None, model="tts-1")

        audio = await provider.synthesize("hello", voice="nova", response_format="mp3")

    # No client constructed, so no possible network call.
    async_openai.assert_not_called()
    assert audio == b""


async def test_missing_key_synthesize_stream_degrades_without_network_call() -> None:
    with patch(f"{_MODULE}.AsyncOpenAI") as async_openai:
        provider = OpenAITTSProvider(api_key=None, model="tts-1")

        stream = provider.synthesize_stream("hello", voice="nova", response_format="mp3")
        assert isinstance(stream, AsyncIterator)
        chunks = [chunk async for chunk in stream]

    async_openai.assert_not_called()
    assert chunks == []
