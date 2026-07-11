from typing import Any

from app.application.scenario.use_cases import ComputeScenarioQuantification
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_quant_node(compute_scenario_quantification: ComputeScenarioQuantification) -> Any:
    """Build the Scenario Simulation graph's Quantification node.

    Thin wrapper: the per-instrument event-study fan-out lives in
    `ComputeScenarioQuantification` (`application/scenario/use_cases/
    compute_scenario_quantification.py`).
    """

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        spec = require_state_value(state.get("spec"), "quant", "spec")
        quant_results = await compute_scenario_quantification.execute(spec)
        return {"quant_results": quant_results}

    return _node
