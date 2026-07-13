from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph

from app.infrastructure.agents.contributor_node import build_contributor_node
from app.infrastructure.agents.personas import (
    ADVISOR_PERSONA,
    ANALYST_PERSONA,
    CONSEQUENCE_PERSONA,
    MACRO_PERSONA,
    OUT_OF_SCOPE_PERSONA,
    QUANT_PERSONA,
    SENTIMENT_PERSONA,
    SMALLTALK_PERSONA,
)
from app.infrastructure.agents.select_specialist_routes import select_specialist_routes
from app.infrastructure.agents.specialist_node_factory import build_specialist_node
from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_router_node import build_supervisor_router_node
from app.infrastructure.agents.supervisor_state import SupervisorState
from app.infrastructure.agents.synthesizer_node import build_synthesizer_node

_SUPERVISOR_NODE = "supervisor"
_CONTRIBUTOR_NODE = "contributor"
_SYNTHESIZER_NODE = "synthesizer"


def build_supervisor_graph(
    router_model: BaseChatModel,
    specialist_model: BaseChatModel,
    checkpointer: Any,
    router_history_max_messages: int,
    history_max_messages: int,
    advisor_tools: list[BaseTool] | None = None,
    analyst_tools: list[BaseTool] | None = None,
    consequence_tools: list[BaseTool] | None = None,
    macro_tools: list[BaseTool] | None = None,
    quant_tools: list[BaseTool] | None = None,
    sentiment_tools: list[BaseTool] | None = None,
    scope_model: BaseChatModel | None = None,
) -> Any:
    """Build the Supervisor graph with a direct path or parallel specialist synthesis.

    One route follows the existing direct specialist path. Multiple routes use LangGraph
    `Send` to run contributor calls in parallel, reduce their typed findings into state,
    and fan in to one synthesizer response. Contributor model tokens are tagged internal;
    only the synthesizer's answer reaches the user-facing token stream.

    Two models, not one (issue #28). `router_model` backs the supervisor node only: picking
    1 of 6 route labels is a pure structured-output classification, exactly the kind of call
    a cheap model is already correct at. `specialist_model` backs all 6 specialist nodes,
    which run a multi-turn tool-calling loop over real analytical work and are the calls most
    likely to be under-served by the cheap tier. Both are built by
    `infrastructure/llm/chat_model_factory.build_chat_model` from a `Settings`-supplied model
    name; the nodes themselves still only depend on `BaseChatModel`, so
    `specialist_node_factory.py` and `supervisor_router_node.py` are unchanged. Passing the
    same model for both arguments reproduces the pre-#28 behavior exactly.

    `router_history_max_messages` bounds how many trailing thread messages the router node reads
    when classifying — the classification only needs the latest turn, so trimming keeps that call
    small. `history_max_messages` is the same idea for the reply-writing nodes: it caps how many
    trailing thread messages the specialist/contributor/synthesizer calls send to the model
    (`Settings.chat_history_max_messages`), bounding per-call prompt growth on long threads. It's
    looser than the router's cap because a reply needs more context than a route pick, and it
    trims only what is SENT — the checkpointer's stored history is untouched. `scope_model`
    (optional; falls back to `specialist_model`, preserving prior behavior)
    backs only the smalltalk / out_of_scope terminals, which are cheap enough for the fast tier;
    the container passes the router model here so greetings and off-topic declines don't spend the
    reasoning tier. Both are latency/cost quick wins and leave every market specialist untouched.

    `advisor_tools`/`analyst_tools`/`consequence_tools`/`macro_tools`/`quant_tools`/
    `sentiment_tools`: optional, additive, default to `None` (reproduces the prior
    behavior exactly for routes with no tools param passed). Each is bound only to its
    own specialist node — see `specialist_node_factory.build_specialist_node`'s `tools`
    param — `advisor_tools` grounds chat replies in persisted signals
    (`infrastructure/agents/tools/build_advisor_grounding_tools.py`),
    `analyst_tools` supplies chart-rendering tools to the `analyst` specialist
    (optional — `analyst` still functions without them, defaulting to text-only
    responses), `consequence_tools` wraps `GenerateConsequenceChain`
    (`infrastructure/agents/tools/build_consequence_tools.py`) so the `consequence`
    specialist always produces a structured causal chain instead of reasoning from
    memory, `macro_tools` wraps `InterpretMacroEvent`
    (`infrastructure/agents/tools/build_macro_tools.py`) so the `macro` specialist
    always grounds asset-class tagging in real FRED/VIX figures, `quant_tools` grounds
    replies in real price stats (`infrastructure/agents/tools/
    build_quant_grounding_tools.py`), and `sentiment_tools` wraps `AnalyzeSentiment`
    (`infrastructure/agents/tools/build_sentiment_tools.py`) so the `sentiment`
    specialist always grounds tone scores in real news + the Fear & Greed index.

    Every node emits `AgentTrace` frames via `get_stream_writer()` (routing/start/
    done — see `supervisor_router_node.py` / `specialist_node_factory.py`);
    `LangGraphAgentRunner.stream` reads them back out with
    `stream_mode=["messages", "custom"]`.

    Compiled with `checkpointer` attached, same as `build_chat_graph` — per-thread
    memory keeps working because specialist nodes only ever return the new `AIMessage`,
    letting `add_messages` append it to the thread's accumulated history.
    """
    graph = StateGraph(SupervisorState)

    graph.add_node(
        _SUPERVISOR_NODE,
        build_supervisor_router_node(router_model, router_history_max_messages),
    )
    personas = {
        SupervisorRoute.ANALYST.value: ANALYST_PERSONA,
        SupervisorRoute.QUANT.value: QUANT_PERSONA,
        SupervisorRoute.ADVISOR.value: ADVISOR_PERSONA,
        SupervisorRoute.CONSEQUENCE.value: CONSEQUENCE_PERSONA,
        SupervisorRoute.MACRO.value: MACRO_PERSONA,
        SupervisorRoute.SENTIMENT.value: SENTIMENT_PERSONA,
    }
    tools_by_route = {
        SupervisorRoute.ANALYST.value: analyst_tools,
        SupervisorRoute.QUANT.value: quant_tools,
        SupervisorRoute.ADVISOR.value: advisor_tools,
        SupervisorRoute.CONSEQUENCE.value: consequence_tools,
        SupervisorRoute.MACRO.value: macro_tools,
        SupervisorRoute.SENTIMENT.value: sentiment_tools,
    }
    graph.add_node(
        _CONTRIBUTOR_NODE,
        build_contributor_node(
            specialist_model, personas, tools_by_route, history_max_messages=history_max_messages
        ),
    )
    graph.add_node(
        _SYNTHESIZER_NODE,
        build_synthesizer_node(specialist_model, history_max_messages=history_max_messages),
    )
    graph.add_node(
        SupervisorRoute.ANALYST.value,
        build_specialist_node(
            "analyst",
            ANALYST_PERSONA,
            specialist_model,
            tools=analyst_tools,
            history_max_messages=history_max_messages,
        ),
    )
    graph.add_node(
        SupervisorRoute.QUANT.value,
        build_specialist_node(
            "quant",
            QUANT_PERSONA,
            specialist_model,
            tools=quant_tools,
            history_max_messages=history_max_messages,
        ),
    )
    graph.add_node(
        SupervisorRoute.ADVISOR.value,
        build_specialist_node(
            "advisor",
            ADVISOR_PERSONA,
            specialist_model,
            tools=advisor_tools,
            history_max_messages=history_max_messages,
        ),
    )
    graph.add_node(
        SupervisorRoute.CONSEQUENCE.value,
        build_specialist_node(
            "consequence",
            CONSEQUENCE_PERSONA,
            specialist_model,
            tools=consequence_tools,
            history_max_messages=history_max_messages,
        ),
    )
    graph.add_node(
        SupervisorRoute.MACRO.value,
        build_specialist_node(
            "macro",
            MACRO_PERSONA,
            specialist_model,
            tools=macro_tools,
            history_max_messages=history_max_messages,
        ),
    )
    graph.add_node(
        SupervisorRoute.SENTIMENT.value,
        build_specialist_node(
            "sentiment",
            SENTIMENT_PERSONA,
            specialist_model,
            tools=sentiment_tools,
            history_max_messages=history_max_messages,
        ),
    )
    # Scope-gate terminals: greetings/meta and off-topic turns. No tools — they answer in a
    # single `model.ainvoke` and can't be talked into running a specialist's analysis or
    # fabricating a market angle. The router (`supervisor_router_node`) classifies here so
    # these turns never reach a market specialist in the first place. They run on `scope_model`
    # (the cheap router tier when the container passes one, else the specialist model) and skip
    # the heavy `MIDAS_PERSONA`/`RESPONSE_FORMAT_GUIDANCE` header (`include_boilerplate=False`) —
    # a greeting or a polite decline needs neither, so both are pure prompt-size savings.
    scope_terminal_model = scope_model or specialist_model
    graph.add_node(
        SupervisorRoute.SMALLTALK.value,
        build_specialist_node(
            "smalltalk",
            SMALLTALK_PERSONA,
            scope_terminal_model,
            tools=None,
            history_max_messages=history_max_messages,
            include_boilerplate=False,
        ),
    )
    graph.add_node(
        SupervisorRoute.OUT_OF_SCOPE.value,
        build_specialist_node(
            "out_of_scope",
            OUT_OF_SCOPE_PERSONA,
            scope_terminal_model,
            tools=None,
            history_max_messages=history_max_messages,
            include_boilerplate=False,
        ),
    )

    graph.set_entry_point(_SUPERVISOR_NODE)
    graph.add_conditional_edges(
        _SUPERVISOR_NODE,
        select_specialist_routes,
        {route.value: route.value for route in SupervisorRoute},
    )
    for route in SupervisorRoute:
        graph.add_edge(route.value, END)
    graph.add_edge(_CONTRIBUTOR_NODE, _SYNTHESIZER_NODE)
    graph.add_edge(_SYNTHESIZER_NODE, END)

    return graph.compile(checkpointer=checkpointer)
