from typing import Any

from app.domain.agents.entities import AgentTrace, AgentTraceEvent


def build_agent_trace_from_payload(payload: dict[str, Any]) -> AgentTrace:
    """Build a domain `AgentTrace` from a LangGraph custom-stream payload.

    Graph nodes write plain dicts via `get_stream_writer()` (see
    `supervisor_router_node.py` / `specialist_node_factory.py`), shaped
    `{"agent": str, "event": str, "detail": str | None}`; `stream_mode="custom"`
    hands that same dict back verbatim on `graph.astream(...)`. This is the one
    place that turns it into the domain entity `LangGraphAgentRunner.stream` yields.
    """
    return AgentTrace(
        agent=payload["agent"],
        event=AgentTraceEvent(payload["event"]),
        detail=payload.get("detail"),
    )
