from typing import Any

from app.application.scenario.use_cases import NormalizeScenarioIntake
from app.infrastructure.agents.scenario.scenario_graph_state import ScenarioGraphState


def build_intake_node(normalize_scenario_intake: NormalizeScenarioIntake) -> Any:
    """Build the Scenario Simulation graph's Intake node.

    Thin wrapper only: all the free-form-vs-preset normalization logic lives in
    `NormalizeScenarioIntake` (`application/scenario/use_cases/
    normalize_scenario_intake.py`) — this node just reads the initial `preset_id`/
    `free_text`/`locale` input state and writes the resulting `ScenarioSpec` back. Passing
    `locale` through (issue #65) makes a free-text spec's title/description come back in the
    user's locale, matching the causal-chain and synthesis steps.
    """

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        spec = await normalize_scenario_intake.execute(
            preset_id=state.get("preset_id"),
            free_text=state.get("free_text"),
            locale=state.get("locale"),
        )
        return {"spec": spec}

    return _node
