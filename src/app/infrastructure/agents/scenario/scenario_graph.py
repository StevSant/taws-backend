from typing import Any

from langgraph.graph import END, StateGraph

from app.application.consequence.use_cases import GenerateConsequenceChain
from app.application.scenario.use_cases import (
    ComputeScenarioQuantification,
    GatherScenarioContext,
    GenerateScenarioAgentContributions,
    NormalizeScenarioIntake,
    SynthesizeScenarioResult,
)
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.agents.scenario.build_agent_panel_node import build_agent_panel_node
from app.infrastructure.agents.scenario.build_causal_chain_node import build_causal_chain_node
from app.infrastructure.agents.scenario.build_compliance_node import build_compliance_node
from app.infrastructure.agents.scenario.build_context_node import build_context_node
from app.infrastructure.agents.scenario.build_intake_node import build_intake_node
from app.infrastructure.agents.scenario.build_quant_node import build_quant_node
from app.infrastructure.agents.scenario.build_synthesis_node import build_synthesis_node
from app.infrastructure.agents.scenario.scenario_graph_state import ScenarioGraphState

_INTAKE_NODE = "intake"
_CONTEXT_NODE = "context"
_CAUSAL_CHAIN_NODE = "causal_chain"
_QUANT_NODE = "quant"
_AGENT_PANEL_NODE = "agent_panel"
_SYNTHESIS_NODE = "synthesis"
_COMPLIANCE_NODE = "compliance"


def build_scenario_graph(
    normalize_scenario_intake: NormalizeScenarioIntake,
    gather_scenario_context: GatherScenarioContext,
    generate_consequence_chain: GenerateConsequenceChain,
    compute_scenario_quantification: ComputeScenarioQuantification,
    generate_agent_contributions: GenerateScenarioAgentContributions,
    synthesize_scenario_result: SynthesizeScenarioResult,
    scenario_repository: ScenarioRepository,
) -> Any:
    """Build the Scenario Simulation graph (issue #12) — the product's signature feature.

    A distinct, standalone `StateGraph`, wired similarly in shape to
    `supervisor_graph.py` (one factory function per node, composed here) but NOT a 5th
    `SupervisorRoute`: this is a single-shot pipeline that runs all six steps for one
    scenario request, not a chat specialist a Supervisor turn routes to. "Reachable via
    chat" is instead satisfied by wrapping this whole graph as one tool
    (`infrastructure/agents/tools/build_scenario_tools.py`), the same shape
    `build_consequence_tools.py` uses to wrap `GenerateConsequenceChain` — see that
    module and `ScenarioSimulationRunner` for the two ways this graph gets invoked (a
    plain single call, not a streamed turn).

    Linear pipeline: Intake -> Context gathering -> Causal chain -> Quantification ->
    Agent panel -> Synthesis -> Compliance -> END. The panel fans out concurrently to
    the six real product specialists and isolates individual failures. Each
    step's OWN internal fan-out (e.g. Context gathering's `asyncio.gather` across
    prices/news/macro/analogs) happens inside that one node rather than as separate
    LangGraph branches — simpler and state-merge-conflict-free, and still literally
    satisfies the issue's "parallel tool calls" ask (see `GatherScenarioContext`'s
    docstring).

    Compiled WITHOUT a checkpointer: unlike the chat/Supervisor graph, this isn't a
    multi-turn conversation with per-thread memory — one `ainvoke(...)` runs one scenario
    request start to finish, and the result is durably recorded via `ScenarioRepository`
    (the Compliance node), not via graph checkpoints.
    """
    graph = StateGraph(ScenarioGraphState)

    graph.add_node(_INTAKE_NODE, build_intake_node(normalize_scenario_intake))
    graph.add_node(_CONTEXT_NODE, build_context_node(gather_scenario_context))
    graph.add_node(_CAUSAL_CHAIN_NODE, build_causal_chain_node(generate_consequence_chain))
    graph.add_node(_QUANT_NODE, build_quant_node(compute_scenario_quantification))
    graph.add_node(_AGENT_PANEL_NODE, build_agent_panel_node(generate_agent_contributions))
    graph.add_node(_SYNTHESIS_NODE, build_synthesis_node(synthesize_scenario_result))
    graph.add_node(_COMPLIANCE_NODE, build_compliance_node(scenario_repository))

    graph.set_entry_point(_INTAKE_NODE)
    graph.add_edge(_INTAKE_NODE, _CONTEXT_NODE)
    graph.add_edge(_CONTEXT_NODE, _CAUSAL_CHAIN_NODE)
    graph.add_edge(_CAUSAL_CHAIN_NODE, _QUANT_NODE)
    graph.add_edge(_QUANT_NODE, _AGENT_PANEL_NODE)
    graph.add_edge(_AGENT_PANEL_NODE, _SYNTHESIS_NODE)
    graph.add_edge(_SYNTHESIS_NODE, _COMPLIANCE_NODE)
    graph.add_edge(_COMPLIANCE_NODE, END)

    return graph.compile()
