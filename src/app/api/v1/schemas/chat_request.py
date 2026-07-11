from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/stream`."""

    message: str = Field(..., description="User message to send to the agent.")
    thread_id: str | None = Field(
        default=None, description="Conversation thread id; omit to start a new thread."
    )
