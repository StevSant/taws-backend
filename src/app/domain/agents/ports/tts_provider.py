from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class TTSProvider(ABC):
    """Port for a Text-to-Speech backend that turns text into spoken-audio bytes.

    Adapters: OpenAI (primary), ElevenLabs, Azure, ... Swapping the backend only means
    adding a new adapter in `infrastructure/tts/` and binding it in the DI container —
    this port never changes. Pure domain: no vendor SDK import may appear here.

    `voice` and `response_format` are plain strings (e.g. `"nova"`, `"mp3"`) so callers
    and the DI container own their values via `Settings` — the port stays vendor-neutral.
    """

    @abstractmethod
    async def synthesize(self, text: str, voice: str, response_format: str) -> bytes:
        """Return the full synthesized audio for `text` as a single `bytes` buffer."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize_stream(
        self, text: str, voice: str, response_format: str
    ) -> AsyncIterator[bytes]:
        """Yield the synthesized audio for `text` as `bytes` chunks as they arrive."""
        raise NotImplementedError
        yield b""  # pragma: no cover — unreachable; keeps this an async generator for typing
