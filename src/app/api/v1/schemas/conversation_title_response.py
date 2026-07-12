from pydantic import BaseModel, Field


class ConversationTitleResponse(BaseModel):
    """Response payload for `POST /api/v1/chat/title`."""

    title: str = Field(..., description="A concise 3-6 word topic title for the conversation.")
