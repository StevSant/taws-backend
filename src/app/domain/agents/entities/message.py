from dataclasses import dataclass

from app.domain.agents.entities.message_role import MessageRole


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message exchanged between a user and an agent."""

    role: MessageRole
    content: str
