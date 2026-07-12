from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/speak`."""

    text: str = Field(
        ...,
        min_length=1,
        description="Text to synthesize into spoken audio.",
    )
    voice: str | None = Field(
        default=None,
        description="Voice to use; omit to use the server-configured default voice.",
    )
