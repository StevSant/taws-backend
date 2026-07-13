import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.application.common import build_locale_instruction
from app.domain.agents.entities import ToolCallEventKind

# Bounds the tool-calling loop below so a model that keeps requesting tools (or a
# misbehaving tool) can never hang a request indefinitely.
_MAX_TOOL_ITERATIONS = 3


def _emit_tool_event(agent_name: str, tool_name: str, event: ToolCallEventKind) -> None:
    try:
        get_stream_writer()(
            {
                "kind": "tool",
                "agent": agent_name,
                "name": tool_name,
                "event": event.value,
            }
        )
    except RuntimeError:
        # Outside a LangGraph runtime (unit tests / direct calls).
        return


async def invoke_with_bound_tools(
    model: BaseChatModel,
    messages: list[BaseMessage],
    tools: list[BaseTool],
    *,
    agent_name: str | None = None,
    locale: str | None = None,
    tags: list[str] | None = None,
    evidence_messages: list[BaseMessage] | None = None,
) -> BaseMessage:
    """Run a bounded tool-calling loop entirely inside one graph node.

    Binds `tools` to `model`, invokes it, executes any requested tool calls, feeds the
    results back, and repeats for up to `_MAX_TOOL_ITERATIONS` rounds (a model can request
    several tools in one turn — each round executes all of them before the next model
    call). This runs entirely within one graph node, without a separate `ToolNode`/
    conditional edge in `supervisor_graph.py`, so the Supervisor graph's shape (one
    specialist node per route) stays unchanged — see `specialist_node_factory.py`'s
    additive `tools` parameter and the backend `CLAUDE.md` "Add a new supervisor
    specialist" section.

    Falls back to a plain `model.ainvoke` if `bind_tools` isn't supported: the fallback
    fake chat model used when no `OPENAI_API_KEY` is configured
    (`infrastructure/llm/fallback_chat_model.build_fallback_chat_model`) raises
    `NotImplementedError` on `bind_tools`, same guard shape as
    `supervisor_router_node.py`'s `with_structured_output` guard.

    When `agent_name` is provided, emits `{"kind": "tool", ...}` custom-stream frames
    before and after each tool invocation so the chat UI can show live tool activity.

    `locale`, when given, is re-asserted as a `SystemMessage` in the LAST position before every
    model call that follows a tool result — the fix for the chat agent answering in English to a
    Spanish user. The caller (`specialist_node_factory`) already puts the locale instruction in
    the system block, but every tool here returns ENGLISH prose (news headlines, signal theses,
    market stats) and those `ToolMessage`s are appended *after* it. The final generation call
    therefore saw a wall of English in the recency slot with the language rule buried far above
    it, and mirrored its input. Re-asserting the rule below the tool output puts it back where
    the model weighs it most. The reminder is added to a throwaway copy per call, never to
    `conversation`, so it can't stack across iterations or leak into the returned message.
    """
    try:
        bound_model = model.bind_tools(tools)
    except NotImplementedError:
        return await model.ainvoke(messages, config={"tags": tags or []})

    tools_by_name = {tool.name: tool for tool in tools}
    conversation = list(messages)
    locale_reminder = [SystemMessage(content=build_locale_instruction(locale))] if locale else []
    tools_have_run = False

    def _prompt() -> list[BaseMessage]:
        """The conversation as sent to the model — locale re-asserted last, once English tool
        output is in play. Before any tool runs there's nothing below the system block to
        countermand, so the prompt is left exactly as the caller built it."""
        return conversation + locale_reminder if tools_have_run else conversation

    async def _run_tool_call(call: dict[str, Any]) -> tuple[BaseMessage, bool]:
        """Execute one requested tool call, emitting its START/DONE frames around the await.

        Returns the resulting `ToolMessage` and whether it came from a real tool (only real
        tool output is mirrored into `evidence_messages`). Standalone so a round's calls can be
        dispatched concurrently with `asyncio.gather`, which preserves input order — the returned
        messages are appended in `tool_calls` order, exactly as the old sequential loop did.
        `_emit_tool_event`'s `get_stream_writer()` reads a contextvar that `asyncio.gather`
        copies into each child task, so the live tool frames still reach the stream from here.
        """
        tool_name = call["name"]
        if agent_name:
            _emit_tool_event(agent_name, tool_name, ToolCallEventKind.START)
        tool = tools_by_name.get(tool_name)
        if tool is None:
            message: BaseMessage = ToolMessage(
                content=f"Unknown tool: {tool_name}", tool_call_id=call["id"]
            )
            from_tool = False
        else:
            message = await tool.ainvoke(call)
            from_tool = True
        if agent_name:
            _emit_tool_event(agent_name, tool_name, ToolCallEventKind.DONE)
        return message, from_tool

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await bound_model.ainvoke(_prompt(), config={"tags": tags or []})
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return response

        conversation.append(response)
        tools_have_run = True
        # This round's tool calls run concurrently; `gather` keeps results in `tool_calls`
        # order, so the ToolMessage/evidence append order is identical to running them serially.
        results = await asyncio.gather(*(_run_tool_call(call) for call in tool_calls))
        for message, from_tool in results:
            conversation.append(message)
            if from_tool and evidence_messages is not None:
                evidence_messages.append(message)

    return await bound_model.ainvoke(_prompt(), config={"tags": tags or []})
