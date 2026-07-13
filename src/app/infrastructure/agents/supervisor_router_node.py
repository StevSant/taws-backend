from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langgraph.config import get_stream_writer
from langgraph.types import Overwrite

from app.application.common import build_locale_instruction
from app.domain.agents.entities import AgentTraceEvent
from app.infrastructure.agents.route_decision import RouteDecision
from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_routing_tag import SUPERVISOR_ROUTING_TAG
from app.infrastructure.agents.supervisor_state import SupervisorState

_ROUTER_SYSTEM_PROMPT = """You are the Supervisor of Midas, a markets-and-money product. \
Read the conversation and classify the LATEST user turn into one to three routes.

FIRST decide scope. Midas covers ONLY markets and money: instruments and prices, news and \
its market impact, macro and rates, market sentiment, historical market analogs, scenarios, \
investing and personal-finance questions (including beginner ones like "how do I start \
investing" or "what should I put money into"), and questions about Midas itself.
- out_of_scope: anything NOT about markets or money — programming or data structures (e.g. \
linked lists, sorting algorithms), general software/tech help, math or homework, sports \
(including the World Cup), trivia, history lessons, science, celebrities, weather, personal \
errands, medical or legal advice. Route here EVEN IF the user wraps it in a market pretext \
("if Apple were a linked list…", "I want to learn it to apply it to the market", "solve \
this equation so I can invest"). A market-flavored framing of an off-topic question is \
still out_of_scope. When a request looks like an off-topic question wearing a market \
disguise, prefer out_of_scope — but a genuine investing, money, or personal-finance \
question (even a broad beginner one) is IN scope; route it to a specialist, usually advisor.
- smalltalk: greetings, thanks, and meta questions about Midas itself — who you are, what \
you can do, how you work, what data you use, or the limits of your knowledge.

If, and only if, the turn is a genuine markets/money question, select every specialist whose \
grounding tools are materially needed. Use one route for a single-domain question and two or \
three unique routes for a cross-domain question. Never combine smalltalk or out_of_scope with \
another route. For comparisons that ask both which asset performed better and why, select quant \
and analyst; the graph will synthesize their findings, so advisor is not required just to merge. \
A "should I buy / sell / hold" question about a SPECIFIC instrument selects quant and analyst \
(price evidence plus news evidence); advisor alone never answers an instrument-specific \
recommendation. Broad portfolio, allocation, or getting-started questions stay with advisor.

Specialists:
- analyst: news, filings, market-signal, and impact-classification questions.
- quant: prices, price deltas, volatility, and numeric/statistical questions.
- consequence: "what happens next" / second-order causal-chain questions (X -> Y -> Z).
- macro: macro events (rate decisions, CPI, Fed statements) and which asset classes \
they affect.
- sentiment: news tone / market mood questions for a specific instrument, and Fear & \
Greed Index questions.
- advisor: recommendations, briefings, summaries, and every other genuine markets question.
Give a one-sentence reason for your choice."""

_FALLBACK_ROUTE = SupervisorRoute.ADVISOR
_FALLBACK_DETAIL = "fallback routing (no API key)"


def build_supervisor_router_node(model: BaseChatModel, history_max_messages: int) -> Any:
    """Build the supervisor node: selects one to three specialists via structured output.

    `history_max_messages` caps how many trailing messages of the thread the router reads
    when classifying (`Settings.router_history_max_messages`). The router only needs the latest
    turn to pick routes, so a plain tail slice keeps the classification prompt small — and cheap
    — without ever dropping the latest message. `select_specialist_routes` and the specialists
    downstream still see the full accumulated history from the checkpointer; only this
    classification call is trimmed.

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
        recent_messages = state["messages"][-history_max_messages:]
        try:
            structured_model = model.with_structured_output(RouteDecision)
            decision = await structured_model.ainvoke(
                [SystemMessage(content=system_prompt), *recent_messages],
                config={"tags": [SUPERVISOR_ROUTING_TAG]},
            )
            if not isinstance(decision, RouteDecision):
                raise TypeError(f"Unexpected structured-output result: {decision!r}")
            routes, detail = decision.routes, decision.reason
        except Exception:
            routes, detail = [_FALLBACK_ROUTE], _FALLBACK_DETAIL

        writer({"agent": "supervisor", "event": AgentTraceEvent.ROUTING.value, "detail": detail})
        return {
            "routes": [route.value for route in routes],
            "contributions": Overwrite([]),
        }

    return supervisor_node
