from pydantic import BaseModel, Field

from app.domain.agents.entities import MessageRole


class RealtimeTurn(BaseModel):
    """One completed voice turn to persist (issue #6): who spoke and the transcript text."""

    role: MessageRole = Field(..., description="Who authored the turn (user or assistant).")
    content: str = Field(..., description="The turn's transcript text.")
