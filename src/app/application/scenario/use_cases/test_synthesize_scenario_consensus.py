from collections.abc import AsyncIterator
from typing import Any

from app.application.scenario.scenario_context import ScenarioContext
from app.application.scenario.use_cases.synthesize_scenario_result import SynthesizeScenarioResult
from app.domain.agents.entities import Message
from app.domain.agents.ports import LLMProvider
from app.domain.consequence.entities import ConsequenceChain
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse
from app.domain.scenario.entities import (
    ScenarioAgentContribution,
    ScenarioAgentId,
    ScenarioContributionStatus,
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioSpec,
)


class _SynthesisProvider(LLMProvider):
    prompt = ""

    async def complete(self, messages: list[Message]) -> str:
        return ""

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        yield ""

    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        self.prompt = messages[-1].content
        return {
            "title": "Panel result",
            "narrative": "Grounded narrative.",
            "impact_map": [
                {
                    "asset_class": "stock",
                    "direction": "uncertain",
                    "confidence": 0.5,
                    "reasoning": "Evidence is limited.",
                }
            ],
            "recommended_actions": ["Monitor data"],
            "consensus": {
                "summary": "Specialists agree evidence is limited.",
                "conclusion": "Keep monitoring.",
                "agreements": ["Evidence is limited"],
                "disagreements": [],
                "uncertainties": ["No live observations"],
                "confidence": 0.4,
            },
        }


class _Universe(InstrumentUniverse):
    def all(self) -> list[Instrument]:
        return []

    def by_symbol(self, symbol: str) -> Instrument | None:
        return None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return []


async def test_synthesis_consumes_panel_and_returns_consensus() -> None:
    provider = _SynthesisProvider()
    contribution = ScenarioAgentContribution(
        agent_id=ScenarioAgentId.ANALYST,
        status=ScenarioContributionStatus.COMPLETED,
        thesis="Analyst grounded thesis",
        confidence=0.7,
        uncertainty="Missing live observations",
    )
    result = await SynthesizeScenarioResult(
        llm_provider=provider,
        instrument_universe=_Universe(),
        max_synthesis_attempts=1,
    ).execute(
        spec=ScenarioSpec(
            entity="TEST",
            event_type="shock",
            magnitude=ScenarioMagnitude.MEDIUM,
            horizon=ScenarioHorizon.SHORT_TERM,
            title="Test",
            description="Test scenario",
            affected_asset_classes=[AssetClass.STOCK],
        ),
        consequence_chain=ConsequenceChain(
            id="chain", subject="test", nodes=[], edges=[], disclaimer="research"
        ),
        context=ScenarioContext(),
        quant_results={},
        agent_contributions=[contribution],
        locale="en",
    )

    assert "Analyst grounded thesis" in provider.prompt
    assert result.agent_contributions == [contribution]
    assert result.consensus is not None
    assert result.consensus.confidence == 0.4
