from typing import TypedDict

from app.domain.agents.entities import Message


class ChatGraphState(TypedDict):
    """State threaded through the minimal single-node chat graph."""

    messages: list[Message]
    reply: str
