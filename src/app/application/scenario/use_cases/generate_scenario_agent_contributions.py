import asyncio
import logging
from collections.abc import Mapping

from pydantic import ValidationError

from app.application.common import build_locale_instruction
from app.application.quant.event_study_stats import EventStudyStats
from app.application.scenario.scenario_agent_contribution_extraction import (
    ScenarioAgentContributionExtraction,
)
from app.application.scenario.scenario_context import ScenarioContext
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities import (
    ScenarioAgentContribution,
    ScenarioAgentId,
    ScenarioContributionStatus,
    ScenarioSpec,
)

logger = logging.getLogger(__name__)
_MAX_GROUNDING_SECTION_CHARS = 6_000

SCENARIO_SPECIALISTS: tuple[ScenarioAgentId, ...] = (
    ScenarioAgentId.ANALYST,
    ScenarioAgentId.QUANT,
    ScenarioAgentId.MACRO,
    ScenarioAgentId.SENTIMENT,
    ScenarioAgentId.CONSEQUENCE,
    ScenarioAgentId.ADVISOR,
)


class GenerateScenarioAgentContributions:
    """Fan out one grounded structured call per real product specialist."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        midas_persona: str,
        specialist_personas: Mapping[ScenarioAgentId, str],
        max_concurrency: int,
        max_attempts: int,
    ) -> None:
        self._llm_provider = llm_provider
        self._midas_persona = midas_persona
        self._specialist_personas = specialist_personas
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._max_attempts = max(1, max_attempts)

    async def execute(
        self,
        *,
        spec: ScenarioSpec,
        context: ScenarioContext,
        consequence_chain: ConsequenceChain,
        quant_results: dict[str, EventStudyStats],
        locale: str,
    ) -> list[ScenarioAgentContribution]:
        grounding = _build_grounding(spec, context, consequence_chain, quant_results)
        return list(
            await asyncio.gather(
                *(
                    self._generate(agent_id, grounding, locale)
                    for agent_id in SCENARIO_SPECIALISTS
                )
            )
        )

    async def _generate(
        self, agent_id: ScenarioAgentId, grounding: str, locale: str
    ) -> ScenarioAgentContribution:
        persona = self._specialist_personas[agent_id]
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=(
                    f"{self._midas_persona}\n\n{persona}\n\n"
                    "For this scenario panel, do not call tools: all available evidence is "
                    "provided below. Return only a structured specialist contribution. "
                    "Never add facts or numbers absent from the grounding. Explicitly state "
                    "missing evidence and uncertainty. Recommendations must be research or "
                    "monitoring actions, never order/execution instructions."
                    + build_locale_instruction(locale)
                ),
            ),
            Message(role=MessageRole.USER, content=grounding),
        ]
        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    raw = await self._llm_provider.complete_structured(
                        messages=messages,
                        schema=ScenarioAgentContributionExtraction.model_json_schema(),
                        schema_name=f"scenario_{agent_id.value}_contribution",
                    )
                    item = ScenarioAgentContributionExtraction.model_validate(raw)
                    return ScenarioAgentContribution(
                        agent_id=agent_id,
                        status=ScenarioContributionStatus.COMPLETED,
                        thesis=item.thesis,
                        confidence=item.confidence,
                        key_findings=item.key_findings,
                        evidence_refs=item.evidence_refs,
                        risks=item.risks,
                        recommendation=item.recommendation,
                        uncertainty=item.uncertainty,
                    )
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Scenario specialist %s failed (attempt %d/%d, %s)",
                        agent_id.value,
                        attempt,
                        self._max_attempts,
                        type(exc).__name__,
                    )
                    if isinstance(exc, ValidationError):
                        continue
        return ScenarioAgentContribution(
            agent_id=agent_id,
            status=ScenarioContributionStatus.FAILED,
            uncertainty="Specialist contribution unavailable.",
            failure_reason=type(last_error).__name__ if last_error else "unknown_error",
        )


def _build_grounding(
    spec: ScenarioSpec,
    context: ScenarioContext,
    chain: ConsequenceChain,
    quant_results: dict[str, EventStudyStats],
) -> str:
    lines = [
        "SCENARIO SPECIFICATION",
        f"- title: {spec.title}",
        f"- entity: {spec.entity}",
        f"- event type: {spec.event_type}",
        f"- magnitude: {spec.magnitude.value}",
        f"- horizon: {spec.horizon.value}",
        f"- description: {spec.description}",
        f"- affected symbols: {', '.join(spec.affected_symbols) or 'none supplied'}",
        "",
        "GATHERED CONTEXT (data objects; absent means unavailable)",
        f"- market stats: {_bounded_repr(context.market_stats)}",
        f"- news items: {_bounded_repr(context.news_items)}",
        f"- macro rates: {_bounded_repr(context.macro_rates)}",
        f"- macro CPI: {_bounded_repr(context.macro_cpi)}",
        f"- volatility regime: {_bounded_repr(context.volatility_regime)}",
        f"- historical analogs: {_bounded_repr(context.historical_analogs)}",
        "",
        "CAUSAL CHAIN",
        *(f"- node {node.id}: {node.label}" for node in chain.nodes),
        *(
            f"- link {edge.source_node_id} -> {edge.target_node_id}: "
            f"{edge.mechanism} (confidence {edge.confidence:.2f})"
            for edge in chain.edges
        ),
        "",
        "QUANTIFICATION",
        *(f"- {symbol}: {_bounded_repr(stats)}" for symbol, stats in quant_results.items()),
    ]
    return "\n".join(lines)


def _bounded_repr(value: object) -> str:
    text = repr(value)
    if len(text) <= _MAX_GROUNDING_SECTION_CHARS:
        return text
    return f"{text[:_MAX_GROUNDING_SECTION_CHARS]}… [truncated]"
