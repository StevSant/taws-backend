from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.config import get_stream_writer

from app.domain.agents.entities import AgentTraceEvent
from app.infrastructure.agents.supervisor_state import SupervisorState


def build_specialist_node(agent_name: str, persona: str, model: BaseChatModel) -> Any:
    """Build a specialist node: invokes `model` with a persona system prompt.

    Shared by every specialist (analyst/quant/advisor) — only `agent_name` and
    `persona` differ, so adding a new specialist never means writing a new node
    function, just a new persona file + a call to this factory (see the backend
    `CLAUDE.md` "Add a new supervisor specialist" section).

    The persona is prepended to the thread's message history for this call only —
    it's never included in the returned state, so it doesn't pile up across turns.
    Emits a `START` trace before invoking the model and a `DONE` trace after, via
    `get_stream_writer()`.

    Returns `Any` (not a `Callable[[SupervisorState], ...]` alias): `StateGraph.add_node`
    expects its callable's `state` parameter to accept the keyword name `state`, which a
    `Callable[...]` type alias erases — annotating with one here makes pyright reject a
    perfectly valid callable at the `add_node` call site in `supervisor_graph.py`.
    """

    async def specialist_node(state: SupervisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({"agent": agent_name, "event": AgentTraceEvent.START.value, "detail": None})

        response = await model.ainvoke([SystemMessage(content=persona), *state["messages"]])

        writer({"agent": agent_name, "event": AgentTraceEvent.DONE.value, "detail": None})
        return {"messages": [response]}

    return specialist_node
