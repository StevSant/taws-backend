from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.agents.entities import Message


@dataclass(slots=True)
class Conversation:
    """A persisted thread of messages belonging to a single user.

    `id` is also the `thread_id` sent to `POST /api/v1/chat/stream`, so the agent
    checkpointer and the `conversations` table are keyed by the same value and cannot
    drift apart.

    `messages` is empty in the summaries returned by `ConversationRepository.list_for_user`
    — the sidebar only needs the title and `updated_at`, and loading every turn of every
    thread just to render a list would be a needless fan-out. Use `get` to load a thread's
    turns.

    `title` is `None` until the frontend calls `POST /api/v1/chat/title` after the first
    exchange; renderers fall back to the first user message.
    """

    id: str
    user_id: str
    title: str | None = None
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
