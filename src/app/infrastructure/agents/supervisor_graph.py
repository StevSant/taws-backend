from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph

from app.infrastructure.agents.personas import (
    ADVISOR_PERSONA,
    ANALYST_PERSONA,
    CONSEQUENCE_PERSONA,
    MACRO_PERSONA,
    QUANT_PERSONA,
    SENTIMENT_PERSONA,
)
from app.infrastructure.agents.select_specialist_route import select_specialist_route
from app.infrastructure.agents.specialist_node_factory import build_specialist_node
from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_router_node import build_supervisor_router_node
from app.infrastructure.agents.supervisor_state import SupervisorState

_SUPERVISOR_NODE = "supervisor"


def build_supervisor_graph(
    model: BaseChatModel,
    checkpointer: Any,
    advisor_tools: list[BaseTool] | None = None,
    consequence_tools: list[BaseTool] | None = None,
    macro_tools: list[BaseTool] | None = None,
    quant_tools: list[BaseTool] | None = None,
    sentiment_tools: list[BaseTool] | None = None,
) -> Any:
    """Build the Supervisor graph: routes each turn to one specialist node.

    Shape: `supervisor` (structured-output routing) -> one of `analyst`/`quant`/
    `advisor`/`consequence`/`macro`/`sentiment` (persona + `model.ainvoke`) -> `END`.
    Uses `SupervisorState` (`MessagesState` + `route`) so the conditional edge out of
    `supervisor` can read the chosen route (`select_specialist_route`) and dispatch to
    the matching node.

    `advisor_tools`/`consequence_tools`/`macro_tools`/`quant_tools`/`sentiment_tools`:
    optional, additive, default to `None` (reproduces the prior behavior exactly for
    routes with no tools param passed). Each is bound only to its own specialist node —
    see `specialist_node_factory.build_specialist_node`'s `tools` param — `advisor_tools`
    grounds chat replies in persisted signals (`infrastructure/agents/tools/
    build_advisor_grounding_tools.py`), `consequence_tools` wraps
    `GenerateConsequenceChain` (`infrastructure/agents/tools/
    build_consequence_tools.py`) so the `consequence` specialist always produces a
    structured causal chain instead of reasoning from memory, `macro_tools` wraps
    `InterpretMacroEvent` (`infrastructure/agents/tools/build_macro_tools.py`) so the
    `macro` specialist always grounds asset-class tagging in real FRED/VIX figures,
    `quant_tools` grounds replies in real price stats (`infrastructure/agents/tools/
    build_quant_grounding_tools.py`), and `sentiment_tools` wraps `AnalyzeSentiment`
    (`infrastructure/agents/tools/build_sentiment_tools.py`) so the `sentiment`
    specialist always grounds tone scores in real news + the Fear & Greed index.
    `analyst` never receives tools.

    Every node emits `AgentTrace` frames via `get_stream_writer()` (routing/start/
    done — see `supervisor_router_node.py` / `specialist_node_factory.py`);
    `LangGraphAgentRunner.stream` reads them back out with
    `stream_mode=["messages", "custom"]`.

    Compiled with `checkpointer` attached, same as `build_chat_graph` — per-thread
    memory keeps working because specialist nodes only ever return the new `AIMessage`,
    letting `add_messages` append it to the thread's accumulated history.
    """
    graph = StateGraph(SupervisorState)

    graph.add_node(_SUPERVISOR_NODE, build_supervisor_router_node(model))
    graph.add_node(
        SupervisorRoute.ANALYST.value, build_specialist_node("analyst", ANALYST_PERSONA, model)
    )
    graph.add_node(
        SupervisorRoute.QUANT.value,
        build_specialist_node("quant", QUANT_PERSONA, model, tools=quant_tools),
    )
    graph.add_node(
        SupervisorRoute.ADVISOR.value,
        build_specialist_node("advisor", ADVISOR_PERSONA, model, tools=advisor_tools),
    )
    graph.add_node(
        SupervisorRoute.CONSEQUENCE.value,
        build_specialist_node("consequence", CONSEQUENCE_PERSONA, model, tools=consequence_tools),
    )
    graph.add_node(
        SupervisorRoute.MACRO.value,
        build_specialist_node("macro", MACRO_PERSONA, model, tools=macro_tools),
    )
    graph.add_node(
        SupervisorRoute.SENTIMENT.value,
        build_specialist_node("sentiment", SENTIMENT_PERSONA, model, tools=sentiment_tools),
    )

    graph.set_entry_point(_SUPERVISOR_NODE)
    graph.add_conditional_edges(
        _SUPERVISOR_NODE,
        select_specialist_route,
        {route.value: route.value for route in SupervisorRoute},
    )
    for route in SupervisorRoute:
        graph.add_edge(route.value, END)

    return graph.compile(checkpointer=checkpointer)
