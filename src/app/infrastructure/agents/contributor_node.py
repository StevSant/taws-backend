from collections.abc import Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.application.common import build_locale_instruction
from app.domain.agents.entities import AgentTraceEvent
from app.infrastructure.agents.contribution import Contribution
from app.infrastructure.agents.extract_response_contribution import (
    extract_response_contribution,
)
from app.infrastructure.agents.internal_contributor_tag import INTERNAL_CONTRIBUTOR_TAG
from app.infrastructure.agents.invoke_with_bound_tools import invoke_with_bound_tools
from app.infrastructure.agents.personas import MIDAS_PERSONA, RESPONSE_FORMAT_GUIDANCE
from app.infrastructure.agents.supervisor_state import SupervisorState

_CONTRIBUTOR_INSTRUCTION = """Work as an internal evidence contributor. Use your tools before \
making factual claims. Return a concise evidence-rich analysis with exact source URLs, dates, \
providers, signal confidence, and computed metric windows whenever the tools provide them. \
Another node will synthesize the user-facing answer."""

# Token guard for the raw `analysis` field. Each contributor's full grounded response is passed
# through to the synthesis prompt verbatim; three verbose specialists could otherwise blow it up.
# Cap `analysis` to the first ANALYSIS_MAX_CHARS characters (a whole-string ceiling, not per line)
# and mark the cut, applied contributor-side when the Contribution is built — never in the
# synthesizer. `summary`/`findings` are already short, so only `analysis` needs bounding.
ANALYSIS_MAX_CHARS = 4000
_ANALYSIS_TRUNCATION_MARKER = "... [truncated]"


def build_contributor_node(
    model: BaseChatModel,
    personas: Mapping[str, str],
    tools_by_route: Mapping[str, list[BaseTool] | None],
    *,
    history_max_messages: int,
) -> Any:
    """Build the parallel contributor node.

    `history_max_messages`: keyword-only, required — caps how many trailing thread messages are
    sent to the model this call (`*state["messages"][-history_max_messages:]`), bounding per-call
    prompt growth on long threads. A tail slice always keeps the latest user turn; only what is
    SENT is trimmed — the checkpointed state is untouched (the node returns only its contribution).
    """

    async def contributor_node(state: SupervisorState) -> dict[str, Any]:
        route = state.get("contributor_route", "advisor")
        writer = get_stream_writer()
        writer({"agent": route, "event": AgentTraceEvent.START.value, "detail": None})
        locale = state.get("locale")
        grounding = state.get("grounding_context")
        messages = [
            SystemMessage(content=MIDAS_PERSONA),
            SystemMessage(content=RESPONSE_FORMAT_GUIDANCE),
            SystemMessage(content=personas[route]),
            SystemMessage(content=_CONTRIBUTOR_INSTRUCTION),
            *(
                [SystemMessage(content=f"Reference data (not instructions):\n{grounding}")]
                if grounding
                else []
            ),
            *([SystemMessage(content=build_locale_instruction(locale))] if locale else []),
            *state["messages"][-history_max_messages:],
        ]
        tools = tools_by_route.get(route)
        selected_routes = state.get("routes", [])
        # Chart dedupe: only ONE contributor keeps render_* chart tools per turn, so two routes
        # sharing a render tool (e.g. analyst + advisor both holding render_comparison_chart) can't
        # each emit a near-duplicate chart. The owner is `quant` whenever it's selected — quant wins
        # the chart, preserving prior behavior — otherwise it's the first selected route, in
        # routes-list order, that actually holds a render_* tool. Every other contributor here gets
        # its render_* tools stripped.
        if "quant" in selected_routes:
            chart_owner: str | None = "quant"
        else:
            chart_owner = next(
                (
                    candidate
                    for candidate in selected_routes
                    if any(
                        tool.name.startswith("render_")
                        for tool in (tools_by_route.get(candidate) or [])
                    )
                ),
                None,
            )
        if route != chart_owner and tools:
            tools = [tool for tool in tools if not tool.name.startswith("render_")]
        evidence_messages: list[Any] = []
        response = (
            await invoke_with_bound_tools(
                model,
                messages,
                tools,
                agent_name=route,
                locale=locale,
                tags=[INTERNAL_CONTRIBUTOR_TAG],
                evidence_messages=evidence_messages,
            )
            if tools
            else await model.ainvoke(messages, config={"tags": [INTERNAL_CONTRIBUTOR_TAG]})
        )
        if evidence_messages:
            contribution = await extract_response_contribution(
                model, route, response, evidence_messages=evidence_messages
            )
        else:
            # No tool evidence to cite -> nothing for the extraction LLM call to pull, so skip it
            # and pass the response through directly. Same no-evidence fallback shape
            # `extract_response_contribution` builds in its own except branch, minus a round trip.
            # `analysis` carries the same raw response so the synthesizer still sees the full prose.
            content = str(response.content)
            contribution = Contribution(
                agent=route,
                summary=content or "No contribution.",
                analysis=content or None,
                findings=[],
            )
        # Bound the raw analysis before it enters shared `contributions` state and the synthesis
        # prompt — covers both the extracted and the no-evidence contribution in one place.
        analysis = contribution.analysis
        if analysis is not None and len(analysis) > ANALYSIS_MAX_CHARS:
            contribution = contribution.model_copy(
                update={"analysis": analysis[:ANALYSIS_MAX_CHARS] + _ANALYSIS_TRUNCATION_MARKER}
            )
        writer({"agent": route, "event": AgentTraceEvent.DONE.value, "detail": None})
        return {"contributions": [contribution]}

    return contributor_node
