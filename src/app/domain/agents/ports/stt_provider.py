from abc import ABC, abstractmethod


class STTProvider(ABC):
    """Port for a Speech-to-Text backend that turns spoken-audio bytes into text.

    The mirror image of `TTSProvider`: instead of text -> audio, it takes an uploaded
    audio clip and returns the transcribed text, so a user can dictate a chat message by
    voice. Adapters: OpenAI Whisper (primary), Deepgram, AssemblyAI, ... Swapping the
    backend only means adding a new adapter in `infrastructure/stt/` and binding it in
    the DI container — this port never changes. Pure domain: no vendor SDK import may
    appear here.

    `filename` and `content_type` come straight from the uploaded file so the adapter
    can hand the vendor a well-formed multipart part; they stay plain strings to keep
    the port vendor-neutral.
    """

    @abstractmethod
    async def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        """Return the transcribed text for the given audio buffer."""
        raise NotImplementedError
