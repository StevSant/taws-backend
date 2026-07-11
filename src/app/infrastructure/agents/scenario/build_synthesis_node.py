from typing import Any

from app.application.scenario.use_cases import SynthesizeScenarioResult
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_synthesis_node(synthesize_scenario_result: SynthesizeScenarioResult) -> Any:
    """Build the Scenario Simulation graph's Synthesis node.

    Thin wrapper: assembling the grounded, UNPERSISTED `ScenarioResult` lives in
    `SynthesizeScenarioResult` (`application/scenario/use_cases/
    synthesize_scenario_result.py`) — persistence itself is the separate Compliance
    node's job (`build_compliance_node.py`).
    """

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        result = await synthesize_scenario_result.execute(
            spec=require_state_value(state.get("spec"), "synthesis", "spec"),
            consequence_chain=require_state_value(
                state.get("consequence_chain"), "synthesis", "consequence_chain"
            ),
            context=require_state_value(state.get("context"), "synthesis", "context"),
            quant_results=require_state_value(
                state.get("quant_results"), "synthesis", "quant_results"
            ),
        )
        return {"result": result}

    return _node
