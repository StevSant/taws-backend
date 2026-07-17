from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from app.domain.agents.entities import (
    AgentStreamEvent,
    ChartEvent,
    CitationsEvent,
    ContributionsEvent,
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
from app.infrastructure.agents.internal_contributor_tag import INTERNAL_CONTRIBUTOR_TAG
from app.infrastructure.agents.locale_config_key import LOCALE_CONFIG_KEY
from app.infrastructure.agents.supervisor_routing_tag import SUPERVISOR_ROUTING_TAG
from app.infrastructure.agents.user_id_config_key import USER_ID_CONFIG_KEY


class LangGraphAgentRunner(AgentRunner):
    """AgentRunner adapter backed by a compiled LangGraph graph (see `build_supervisor_graph`).

    Runs `graph.astream(..., stream_mode=["messages", "custom"])`. Passing a *list* of
    stream modes changes the yielded shape from LangGraph: instead of the bare
    per-mode payload, each iteration yields a `(mode, payload)` tuple —
    - `mode == "messages"`: `payload` is the same `(message_chunk, metadata)` tuple as
      the single-mode case. `metadata` is inspected for the `SUPERVISOR_ROUTING_TAG` run
      tag (set on the supervisor's `with_structured_output(...).ainvoke(...)` call in
      `supervisor_router_node.py`) so its structured-output chunks — raw routing JSON
      like `{"routes": ["..."], "reason": "..."}` — are skipped instead of leaking into
      the SSE token stream. `INTERNAL_CONTRIBUTOR_TAG` hides parallel contributor and
      citation-extraction tokens for the same reason.
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
        # `locale` goes out on BOTH channels, because the graph has two kinds of consumer and
        # they can't read the same one:
        # - the supervisor/specialist NODES read `state["locale"]` (they already take `state`);
        # - the TOOLS read `config["configurable"]["locale"]`, since a tool is invoked from
        #   inside a node by `invoke_with_bound_tools` and never sees the state. LangChain
        #   injects this config into any tool coroutine declaring a `RunnableConfig` parameter
        #   — see `tools/resolve_tool_locale.py`.
        # Same value, one resolution (`ResolveLocale`), so the two can't disagree.
        config = {
            "configurable": {
                "thread_id": thread_id,
                USER_ID_CONFIG_KEY: user_id,
                LOCALE_CONFIG_KEY: locale,
            }
        }
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
                    hidden_tags = {SUPERVISOR_ROUTING_TAG, INTERNAL_CONTRIBUTOR_TAG}
                    if hidden_tags.intersection(metadata.get("tags", [])):
                        continue
                    token = extract_ai_message_token(message_chunk)
                    if token:
                        yield TokenEvent(token=token)
                elif mode == "custom":
                    kind = payload.get("kind")
                    if kind == "chart":
                        yield ChartEvent(chart=payload["chart"])
                    elif kind == "citations":
                        yield CitationsEvent(citations=payload["citations"])
                    elif kind == "contributions":
                        yield ContributionsEvent(contributions=payload["contributions"])
                    elif kind == "tool":
                        yield ToolCallEvent(tool=build_tool_call_from_payload(payload))
                    else:
                        yield TraceEvent(trace=build_agent_trace_from_payload(payload))
        except Exception as exc:  # last-resort guard, see class docstring
            yield ErrorEvent(message=str(exc))
