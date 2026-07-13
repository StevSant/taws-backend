from dataclasses import dataclass, field
from typing import Any

from app.domain.agents.entities.message_role import MessageRole


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message exchanged between a user and an agent.

    `charts` carries the charts an assistant turn produced, as already-serialized ChartSpec
    wire dicts (the same shape streamed over SSE — see `ChartEvent`). It is persisted with the
    turn so a reopened thread (even on another device, or after a full reload) re-renders the
    charts the user saw, instead of a text-only transcript. Empty for user turns and for
    assistant turns that drew nothing; the agent graph ignores it entirely — only the
    conversation-persistence path reads or writes it.
    """

    role: MessageRole
    content: str
    charts: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
