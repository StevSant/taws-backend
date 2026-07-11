from typing import NotRequired, TypedDict

from app.application.quant.event_study_stats import EventStudyStats
from app.application.scenario.scenario_context import ScenarioContext
from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities import ScenarioResult, ScenarioSpec


class ScenarioGraphState(TypedDict):
    """Graph state for `build_scenario_graph`: threads a scenario run through Intake ->
    Context gathering -> Causal chain -> Quantification -> Synthesis -> Compliance.

    `preset_id`/`free_text` are the only fields present in the initial input state (see
    `ScenarioSimulationRunner.execute`); every other field is written by the node that
    produces it and is absent until then, hence `NotRequired` — same shape as
    `SupervisorState.route`. Not a `MessagesState` subclass: this graph runs a single
    request/response pipeline, not a conversational thread.

    Every node past Intake reads one or more of these `NotRequired` fields; see
    `require_state_value` below for how they're read without an unchecked
    `state["key"]` subscript.
    """

    preset_id: NotRequired[str | None]
    free_text: NotRequired[str | None]
    spec: NotRequired[ScenarioSpec]
    context: NotRequired[ScenarioContext]
    consequence_chain: NotRequired[ConsequenceChain]
    quant_results: NotRequired[dict[str, EventStudyStats]]
    result: NotRequired[ScenarioResult]


def require_state_value[T](value: T | None, node_name: str, key: str) -> T:
    """Narrow a `NotRequired` `ScenarioGraphState` field, raising a clear error if a
    future graph-wiring change ever lets a node run before its dependency is set.

    Every mid-pipeline field is `NotRequired` because it's genuinely absent from the
    graph's initial input state — but `scenario_graph.py`'s strictly linear edge order
    guarantees each field is already populated by the time any later node reads it. This
    turns that edge-order guarantee into an explicit, pyright-clean runtime check
    (`state.get(key)` + this helper) instead of an unchecked `state["key"]` access, which
    `reportTypedDictNotRequiredAccess` correctly flags as unsafe on its own.
    """
    if value is None:
        raise RuntimeError(f"Scenario graph: {node_name} node ran before '{key}' was set.")
    return value
