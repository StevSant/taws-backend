from app.api.v1.schemas import ScenarioResultResponse
from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities import (
    ScenarioAgentContribution,
    ScenarioAgentId,
    ScenarioConsensus,
    ScenarioContributionStatus,
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioResult,
    ScenarioSpec,
)
from app.infrastructure.persistence.scenario_row_mapper import scenario_from_row, scenario_to_row


def _result() -> ScenarioResult:
    return ScenarioResult(
        id="9d90824f-3f35-466b-81ab-c72f91b73e1e",
        spec=ScenarioSpec(
            entity="TEST",
            event_type="shock",
            magnitude=ScenarioMagnitude.MEDIUM,
            horizon=ScenarioHorizon.SHORT_TERM,
            title="Test",
            description="Test",
        ),
        title="Result",
        narrative="Narrative",
        impact_map=[],
        consequence_chain=ConsequenceChain(
            id="chain", subject="test", nodes=[], edges=[], disclaimer="research"
        ),
        recommended_actions=[],
        disclaimer="research",
        agent_contributions=[
            ScenarioAgentContribution(
                agent_id=ScenarioAgentId.QUANT,
                status=ScenarioContributionStatus.COMPLETED,
                thesis="Quant thesis",
                confidence=0.8,
            )
        ],
        consensus=ScenarioConsensus(summary="Summary", conclusion="Conclusion", confidence=0.7),
    )


def test_scenario_consensus_round_trip() -> None:
    mapped = scenario_from_row(scenario_to_row(_result()))

    assert mapped.agent_contributions[0].agent_id is ScenarioAgentId.QUANT
    assert mapped.agent_contributions[0].thesis == "Quant thesis"
    assert mapped.consensus is not None
    assert mapped.consensus.conclusion == "Conclusion"


def test_legacy_scenario_row_defaults_panel_fields() -> None:
    row = scenario_to_row(_result())
    row.pop("agent_contributions")
    row.pop("consensus")

    mapped = scenario_from_row(row)

    assert mapped.agent_contributions == []
    assert mapped.consensus is None
    response = ScenarioResultResponse.model_validate(mapped)
    assert response.agent_contributions == []
    assert response.consensus is None
