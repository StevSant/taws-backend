from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, MessagesState, StateGraph


def build_chat_graph(model: BaseChatModel, checkpointer: Any) -> Any:
    """Build a minimal single-node LangGraph graph that calls `model`.

    Kept intentionally small for the hackathon skeleton: one node, no branching, no
    tools. Extend with more nodes/conditional edges/tools as agents are added in
    Phase 2+ (see architecture spec, section 8) — the graph shape is the only thing
    that changes; ports/adapters stay the same.

    Uses `langgraph.graph.MessagesState` (`{"messages": Annotated[list, add_messages]}`)
    as the graph state, and compiles with `checkpointer` attached. Because the node
    returns only the newly generated `AIMessage`, `add_messages` appends it to the
    thread's accumulated history instead of replacing it — combined with the
    checkpointer keying state by `thread_id` (see `LangGraphAgentRunner.stream`),
    this is what gives the graph multi-turn memory per thread instead of amnesia.

    `model` is any LangChain `BaseChatModel` — see `infrastructure/llm/chat_model_factory.
    build_chat_model` for the provider swap point; this function never imports a
    vendor SDK directly.
    """

    async def call_model(state: MessagesState) -> MessagesState:
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.set_entry_point("call_model")
    graph.add_edge("call_model", END)
    return graph.compile(checkpointer=checkpointer)
