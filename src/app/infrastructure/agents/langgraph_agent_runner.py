from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    ErrorEvent,
    Message,
    TokenEvent,
    ToolCallEvent,
    TraceEvent,
)
from app.domain.agents.ports import AgentRunner
from app.infrastructure.agents.build_agent_trace_from_payload import (
    build_agent_trace_from_payload,
)
from app.infrastructure.agents.build_tool_call_from_payload import build_tool_call_from_payload
from app.infrastructure.agents.extract_ai_message_token import extract_ai_message_token
from app.infrastructure.agents.supervisor_routing_tag import SUPERVISOR_ROUTING_TAG


class LangGraphAgentRunner(AgentRunner):
    """AgentRunner adapter backed by a compiled LangGraph graph (see `build_supervisor_graph`).

    Runs `graph.astream(..., stream_mode=["messages", "custom"])`. Passing a *list* of
    stream modes changes the yielded shape from LangGraph: instead of the bare
    per-mode payload, each iteration yields a `(mode, payload)` tuple —
    - `mode == "messages"`: `payload` is the same `(message_chunk, metadata)` tuple as
      the single-mode case. `metadata` is inspected for the `SUPERVISOR_ROUTING_TAG` run
      tag (set on the supervisor's `with_structured_output(...).ainvoke(...)` call in
      `supervisor_router_node.py`) so its structured-output chunks — raw routing JSON
      like `{"route": "...", "reason": "..."}` — are skipped instead of leaking into the
      SSE token stream ahead of the chosen specialist's real answer text.
    - `mode == "custom"`: `payload` is exactly the dict a node passed to
      `get_stream_writer()()` (see `supervisor_router_node.py` /
      `specialist_node_factory.py`), untouched by LangGraph.

    Tokens become `TokenEvent`s, custom trace payloads become `TraceEvent`s. Any
    exception during the run is caught and yielded as a single `ErrorEvent` instead of
    propagating — so a failure mid-stream still reaches the SSE client as a well-formed
    frame instead of dropping the connection (see `api/v1/routers/chat.py`'s `_to_sse`).

    An optional `grounding_context` (issue #73) is threaded into the graph's initial
    input state so the specialist node can anchor its reply on a referenced asset/news
    article; omitted from the state when `None`, leaving behavior unchanged.
    """

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def stream(
        self,
        thread_id: str,
        message: Message,
        user_id: str,
        locale: str,
        grounding_context: str | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        # `locale` is re-sent on every turn (issue #67): a user who switches language
        # mid-thread must be answered in the new one, and the checkpointed state's
        # last-value-wins reducer makes the newest turn's locale the effective one.
        input_state: dict[str, Any] = {
            "messages": [HumanMessage(content=message.content)],
            "locale": locale,
        }
        if grounding_context:
            input_state["grounding_context"] = grounding_context

        try:
            async for mode, payload in self._graph.astream(
                input_state, config=config, stream_mode=["messages", "custom"]
            ):
                if mode == "messages":
                    message_chunk, metadata = payload
                    if SUPERVISOR_ROUTING_TAG in metadata.get("tags", []):
                        continue
                    token = extract_ai_message_token(message_chunk)
                    if token:
                        yield TokenEvent(token=token)
                elif mode == "custom":
                    kind = payload.get("kind")
                    if kind == "chart":
                        yield ChartEvent(chart=payload["chart"])
                    elif kind == "tool":
                        yield ToolCallEvent(tool=build_tool_call_from_payload(payload))
                    else:
                        yield TraceEvent(trace=build_agent_trace_from_payload(payload))
        except Exception as exc:  # last-resort guard, see class docstring
            yield ErrorEvent(message=str(exc))
