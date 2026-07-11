from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

# Bounds the tool-calling loop below so a model that keeps requesting tools (or a
# misbehaving tool) can never hang a request indefinitely.
_MAX_TOOL_ITERATIONS = 3


async def invoke_with_bound_tools(
    model: BaseChatModel, messages: list[BaseMessage], tools: list[BaseTool]
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
    """
    try:
        bound_model = model.bind_tools(tools)
    except NotImplementedError:
        return await model.ainvoke(messages)

    tools_by_name = {tool.name: tool for tool in tools}
    conversation = list(messages)

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await bound_model.ainvoke(conversation)
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return response

        conversation.append(response)
        for call in tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                conversation.append(
                    ToolMessage(content=f"Unknown tool: {call['name']}", tool_call_id=call["id"])
                )
                continue
            conversation.append(await tool.ainvoke(call))

    return await bound_model.ainvoke(conversation)
