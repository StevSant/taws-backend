from dataclasses import dataclass

from app.domain.agents.entities.tool_call_event_kind import ToolCallEventKind


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool invocation hop surfaced over the chat SSE stream."""

    agent: str
    name: str
    event: ToolCallEventKind
