from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.application.common import build_locale_instruction
from app.domain.agents.entities import AgentTraceEvent
from app.infrastructure.agents.invoke_with_bound_tools import invoke_with_bound_tools
from app.infrastructure.agents.personas import MIDAS_PERSONA, RESPONSE_FORMAT_GUIDANCE
from app.infrastructure.agents.supervisor_state import SupervisorState


def build_specialist_node(
    agent_name: str,
    persona: str,
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
) -> Any:
    """Build a specialist node: invokes `model` with a persona system prompt.

    Shared by every specialist (analyst/quant/advisor) — only `agent_name` and
    `persona` differ, so adding a new specialist never means writing a new node
    function, just a new persona file + a call to this factory (see the backend
    `CLAUDE.md` "Add a new supervisor specialist" section).

    The top-level `MIDAS_PERSONA` identity is prepended above the specialist `persona`
    so every reply carries the Midas voice while keeping the specialist's behavior; both
    are prepended to the thread's message history for this call only — never included in
    the returned state, so they don't pile up across turns.
    Emits a `START` trace before invoking the model and a `DONE` trace after, via
    `get_stream_writer()`.

    Every persona above is authored in English, so without a locale instruction the model
    simply answers in English no matter what the UI is set to (issue #67). `state["locale"]`
    — resolved per turn and written into the state by `LangGraphAgentRunner.stream` — is
    appended LAST, after the personas, so it overrides the language they're written in for
    all six specialists at once. It's the same `build_locale_instruction` the signal/
    briefing/scenario pipelines already use, so chat can't drift to a different phrasing.

    `tools`: optional, additive, defaults to `None` (unchanged behavior — a single plain
    `model.ainvoke`). When given (today only the `advisor` route, see
    `supervisor_graph.py` / `core/di/container.py`), the node runs a bounded tool-calling
    loop instead (`invoke_with_bound_tools`) so it can ground its reply in persisted data
    (signals/briefings/watchlists). `analyst`/`quant` keep calling this with `tools=None`
    and are completely unaffected.

    Returns `Any` (not a `Callable[[SupervisorState], ...]` alias): `StateGraph.add_node`
    expects its callable's `state` parameter to accept the keyword name `state`, which a
    `Callable[...]` type alias erases — annotating with one here makes pyright reject a
    perfectly valid callable at the `add_node` call site in `supervisor_graph.py`.
    """

    async def specialist_node(state: SupervisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        writer({"agent": agent_name, "event": AgentTraceEvent.START.value, "detail": None})

        locale = state.get("locale")
        messages = [
            SystemMessage(content=MIDAS_PERSONA),
            SystemMessage(content=RESPONSE_FORMAT_GUIDANCE),
            SystemMessage(content=persona),
            *([SystemMessage(content=build_locale_instruction(locale))] if locale else []),
            *state["messages"],
        ]
        response = (
            await invoke_with_bound_tools(model, messages, tools, agent_name=agent_name)
            if tools
            else await model.ainvoke(messages)
        )

        writer({"agent": agent_name, "event": AgentTraceEvent.DONE.value, "detail": None})
        return {"messages": [response]}

    return specialist_node
