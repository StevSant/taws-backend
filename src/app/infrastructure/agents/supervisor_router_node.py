from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.config import get_stream_writer

from app.application.common import build_locale_instruction
from app.domain.agents.entities import AgentTraceEvent
from app.infrastructure.agents.route_decision import RouteDecision
from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_routing_tag import SUPERVISOR_ROUTING_TAG
from app.infrastructure.agents.supervisor_state import SupervisorState

_ROUTER_SYSTEM_PROMPT = """You are the Supervisor of a team of financial-research \
specialists. Read the conversation and pick exactly one specialist to handle the \
latest user turn:
- analyst: news, filings, market-signal, and impact-classification questions.
- quant: prices, price deltas, volatility, and numeric/statistical questions.
- consequence: "what happens next" / second-order causal-chain questions (X -> Y -> Z).
- macro: macro events (rate decisions, CPI, Fed statements) and which asset classes \
they affect.
- sentiment: news tone / market mood questions for a specific instrument, and Fear & \
Greed Index questions.
- advisor: recommendations, briefings, summaries, and everything else.
Give a one-sentence reason for your choice."""

_FALLBACK_ROUTE = SupervisorRoute.ADVISOR
_FALLBACK_DETAIL = "fallback routing (no API key)"


def build_supervisor_router_node(model: BaseChatModel) -> Any:
    """Build the "supervisor" node: picks a specialist via structured output.

    Uses `model.with_structured_output(RouteDecision)` to force the model to return
    one of `SupervisorRoute` plus a short reason. The fallback fake chat model (used
    when no API key is configured, see `chat_model_factory.build_chat_model`) doesn't
    implement `bind_tools`/structured output and raises `NotImplementedError` as soon
    as `with_structured_output` is called — caught here and routed to `advisor` by
    default so the graph keeps working without a key.

    Emits one `ROUTING` trace via `get_stream_writer()` before returning the chosen
    route in `SupervisorState.route`, which `select_specialist_route` reads to choose
    the conditional edge.

    Returns `Any` (not a `Callable[[SupervisorState], ...]` alias): `StateGraph.add_node`
    expects its callable's `state` parameter to accept the keyword name `state`, which a
    `Callable[...]` type alias erases — annotating with one here makes pyright reject a
    perfectly valid callable at the `add_node` call site in `supervisor_graph.py`.

    The structured-output `ainvoke` call is tagged with `SUPERVISOR_ROUTING_TAG` so
    `LangGraphAgentRunner.stream` can recognize and skip its chunks in the
    `stream_mode="messages"` branch — otherwise the raw routing JSON would leak into the
    SSE token stream ahead of the chosen specialist's real answer text.

    The router's `reason` is not internal-only: it's surfaced to the user as the `detail` of
    the `ROUTING` trace the chat UI renders. So the turn's `state["locale"]` (issue #67) is
    appended to this English prompt too — otherwise a Spanish session would still see an
    English routing rationale above an otherwise-Spanish reply. The route *label* itself is
    an enum value and stays language-independent.
    """

    async def supervisor_node(state: SupervisorState) -> dict[str, Any]:
        writer = get_stream_writer()
        locale = state.get("locale")
        system_prompt = _ROUTER_SYSTEM_PROMPT + (build_locale_instruction(locale) if locale else "")
        try:
            structured_model = model.with_structured_output(RouteDecision)
            decision = await structured_model.ainvoke(
                [SystemMessage(content=system_prompt), *state["messages"]],
                config={"tags": [SUPERVISOR_ROUTING_TAG]},
            )
            if not isinstance(decision, RouteDecision):
                raise TypeError(f"Unexpected structured-output result: {decision!r}")
            route, detail = decision.route, decision.reason
        except Exception:
            route, detail = _FALLBACK_ROUTE, _FALLBACK_DETAIL

        writer({"agent": "supervisor", "event": AgentTraceEvent.ROUTING.value, "detail": detail})
        return {"route": route.value}

    return supervisor_node
