from typing import Any

from app.application.scenario.use_cases import GenerateScenarioAgentContributions
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_agent_panel_node(
    generate_contributions: GenerateScenarioAgentContributions,
) -> Any:
    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        contributions = await generate_contributions.execute(
            spec=require_state_value(state.get("spec"), "agent_panel", "spec"),
            context=require_state_value(state.get("context"), "agent_panel", "context"),
            consequence_chain=require_state_value(
                state.get("consequence_chain"), "agent_panel", "consequence_chain"
            ),
            quant_results=require_state_value(
                state.get("quant_results"), "agent_panel", "quant_results"
            ),
            locale=require_state_value(state.get("locale"), "agent_panel", "locale"),
        )
        return {"agent_contributions": contributions}

    return _node
