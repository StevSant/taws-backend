from typing import Any

from app.domain.agents.entities import ToolCall, ToolCallEventKind


def build_tool_call_from_payload(payload: dict[str, Any]) -> ToolCall:
    """Build a domain `ToolCall` from a LangGraph custom-stream tool payload."""
    return ToolCall(
        agent=payload["agent"],
        name=payload["name"],
        event=ToolCallEventKind(payload["event"]),
    )
