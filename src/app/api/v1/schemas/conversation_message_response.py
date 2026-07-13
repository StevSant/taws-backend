from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.agents.entities import MessageRole


class ConversationMessageResponse(BaseModel):
    """One persisted turn of a conversation, as returned by `GET /chat/conversations/{id}`.

    `charts` are the already-serialized ChartSpec wire dicts the assistant produced on this
    turn (the same shape streamed live over SSE), so a reopened thread re-renders them instead
    of dropping to a text-only transcript. Empty for user turns and text-only replies.
    """

    model_config = ConfigDict(from_attributes=True)

    role: MessageRole
    content: str
    charts: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
