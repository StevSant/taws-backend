from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.agents.entities import Message


@dataclass(slots=True)
class Conversation:
    """A persisted thread of messages belonging to a single user."""

    id: str
    user_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
