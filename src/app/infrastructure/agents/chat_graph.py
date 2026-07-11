from typing import Any

from langgraph.graph import END, StateGraph

from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.infrastructure.agents.chat_graph_state import ChatGraphState


def build_chat_graph(llm_provider: LLMProvider) -> Any:
    """Build a minimal single-node LangGraph graph that calls `llm_provider`.

    Kept intentionally small for the hackathon skeleton: one node, no branching, no
    tools. Extend with more nodes/conditional edges/tools as agents are added in
    Phase 2+ (see architecture spec, section 8) — the graph shape is the only thing
    that changes; ports/adapters stay the same.
    """

    async def call_model(state: ChatGraphState) -> ChatGraphState:
        reply = await llm_provider.complete(state["messages"])
        return {
            "messages": [*state["messages"], Message(role=MessageRole.ASSISTANT, content=reply)],
            "reply": reply,
        }

    graph = StateGraph(ChatGraphState)
    graph.add_node("call_model", call_model)
    graph.set_entry_point("call_model")
    graph.add_edge("call_model", END)
    return graph.compile()
