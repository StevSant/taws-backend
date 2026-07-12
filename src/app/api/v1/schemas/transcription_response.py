from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    """Response payload for `POST /api/v1/chat/transcribe`."""

    text: str = Field(
        ...,
        description="Text transcribed from the uploaded audio clip.",
    )
