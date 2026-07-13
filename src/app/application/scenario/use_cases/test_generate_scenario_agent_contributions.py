import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.application.scenario.scenario_context import ScenarioContext
from app.application.scenario.use_cases.generate_scenario_agent_contributions import (
    SCENARIO_SPECIALISTS,
    GenerateScenarioAgentContributions,
)
from app.domain.agents.entities import Message
from app.domain.agents.ports import LLMProvider
from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities import (
    ScenarioAgentId,
    ScenarioContributionStatus,
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioSpec,
)


class _ConcurrentProvider(LLMProvider):
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def complete(self, messages: list[Message]) -> str:
        return ""

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        yield ""

    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            if "macro" in schema_name:
                raise RuntimeError("provider unavailable")
            return {
                "thesis": schema_name,
                "confidence": 0.7,
                "key_findings": ["grounded finding"],
                "evidence_refs": [],
                "risks": ["missing data"],
                "recommendation": "Monitor evidence",
                "uncertainty": "Context is incomplete.",
            }
        finally:
            self.active -= 1


async def test_fans_out_concurrently_and_isolates_one_specialist_failure() -> None:
    provider = _ConcurrentProvider()
    use_case = GenerateScenarioAgentContributions(
        llm_provider=provider,
        midas_persona="Midas",
        specialist_personas={agent_id: agent_id.value for agent_id in SCENARIO_SPECIALISTS},
        max_concurrency=3,
        max_attempts=1,
    )

    contributions = await use_case.execute(
        spec=ScenarioSpec(
            entity="TEST",
            event_type="shock",
            magnitude=ScenarioMagnitude.MEDIUM,
            horizon=ScenarioHorizon.SHORT_TERM,
            title="Test scenario",
            description="Grounded test",
        ),
        context=ScenarioContext(),
        consequence_chain=ConsequenceChain(
            id="chain", subject="test", nodes=[], edges=[], disclaimer="research"
        ),
        quant_results={},
        locale="en",
    )

    assert len(contributions) == 6
    assert provider.max_active == 3
    failed = [item for item in contributions if item.status is ScenarioContributionStatus.FAILED]
    assert [item.agent_id for item in failed] == [ScenarioAgentId.MACRO]
    assert failed[0].thesis == ""
    assert sum(item.status is ScenarioContributionStatus.COMPLETED for item in contributions) == 5
