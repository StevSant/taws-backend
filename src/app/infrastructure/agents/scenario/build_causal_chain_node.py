from typing import Any

from app.application.consequence.use_cases import GenerateConsequenceChain
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_causal_chain_node(generate_consequence_chain: GenerateConsequenceChain) -> Any:
    """Build the Scenario Simulation graph's Causal chain node.

    Calls `GenerateConsequenceChain.execute(subject)` directly (issue #8's reusable use
    case — see that class's docstring, which explicitly anticipates this call site) with
    a subject derived from the `ScenarioSpec`'s `entity` + `description`, so the causal
    chain reasons about the actual normalized scenario, not just a bare entity name.
    """

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        spec = require_state_value(state.get("spec"), "causal_chain", "spec")
        subject = f"{spec.entity}: {spec.description}"
        chain = await generate_consequence_chain.execute(subject)
        return {"consequence_chain": chain}

    return _node
