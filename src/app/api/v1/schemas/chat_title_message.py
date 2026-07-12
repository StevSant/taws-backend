from pydantic import BaseModel, Field

from app.domain.agents.entities import MessageRole


class ChatTitleMessage(BaseModel):
    """One conversation message supplied to the title-generation endpoint."""

    role: MessageRole = Field(..., description="Who authored the message.")
    content: str = Field(..., description="The message text.")
