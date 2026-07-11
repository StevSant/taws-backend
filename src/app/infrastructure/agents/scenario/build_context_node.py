from typing import Any

from app.application.scenario.use_cases import GatherScenarioContext
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_context_node(gather_scenario_context: GatherScenarioContext) -> Any:
    """Build the Scenario Simulation graph's Context gathering node.

    Thin wrapper: the parallel prices/news/macro/analogs fetch (`asyncio.gather`) lives in
    `GatherScenarioContext` (`application/scenario/use_cases/gather_scenario_context.py`).
    """

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        spec = require_state_value(state.get("spec"), "context", "spec")
        context = await gather_scenario_context.execute(spec)
        return {"context": context}

    return _node
