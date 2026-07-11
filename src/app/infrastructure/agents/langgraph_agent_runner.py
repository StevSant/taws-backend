from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from app.domain.agents.entities import AgentStreamEvent, ErrorEvent, Message, TokenEvent, TraceEvent
from app.domain.agents.ports import AgentRunner
from app.infrastructure.agents.build_agent_trace_from_payload import (
    build_agent_trace_from_payload,
)
from app.infrastructure.agents.extract_ai_message_token import extract_ai_message_token


class LangGraphAgentRunner(AgentRunner):
    """AgentRunner adapter backed by a compiled LangGraph graph (see `build_supervisor_graph`).

    Runs `graph.astream(..., stream_mode=["messages", "custom"])`. Passing a *list* of
    stream modes changes the yielded shape from LangGraph: instead of the bare
    per-mode payload, each iteration yields a `(mode, payload)` tuple —
    - `mode == "messages"`: `payload` is the same `(message_chunk, metadata)` tuple as
      the single-mode case; `metadata` is unused, kept in the unpack for clarity.
    - `mode == "custom"`: `payload` is exactly the dict a node passed to
      `get_stream_writer()()` (see `supervisor_router_node.py` /
      `specialist_node_factory.py`), untouched by LangGraph.

    Tokens become `TokenEvent`s, custom trace payloads become `TraceEvent`s. Any
    exception during the run is caught and yielded as a single `ErrorEvent` instead of
    propagating — so a failure mid-stream still reaches the SSE client as a well-formed
    frame instead of dropping the connection (see `api/v1/routers/chat.py`'s `_to_sse`).
    """

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def stream(self, thread_id: str, message: Message) -> AsyncIterator[AgentStreamEvent]:
        config = {"configurable": {"thread_id": thread_id}}
        input_state = {"messages": [HumanMessage(content=message.content)]}

        try:
            async for mode, payload in self._graph.astream(
                input_state, config=config, stream_mode=["messages", "custom"]
            ):
                if mode == "messages":
                    message_chunk, _metadata = payload
                    token = extract_ai_message_token(message_chunk)
                    if token:
                        yield TokenEvent(token=token)
                elif mode == "custom":
                    yield TraceEvent(trace=build_agent_trace_from_payload(payload))
        except Exception as exc:  # last-resort guard, see class docstring
            yield ErrorEvent(message=str(exc))
