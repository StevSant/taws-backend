from dataclasses import replace
from typing import Any

from app.application.compliance import ComplianceViolationError
from app.application.compliance.use_cases import ReviewCompliance
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.agents.scenario.scenario_graph_state import (
    ScenarioGraphState,
    require_state_value,
)


def build_compliance_node(scenario_repository: ScenarioRepository) -> Any:
    """Build the Scenario Simulation graph's Compliance node — the final gate before
    persistence (issue #9), same "reject rather than silently persist" contract as
    `GenerateSignal`/`GenerateBriefing`.

    Reviews the synthesized `ScenarioResult`'s disclaimer plus every free-text field an
    LLM could have authored: the narrative, the recommended actions, and every evidence
    item's `detail` (the `[dato actual]`/`[análogo histórico]` ones are code-generated and
    safe by construction, but scanning them too is cheap and simpler than filtering them
    out). Raises the existing `ComplianceViolationError` on failure — this graph node
    intentionally does NOT catch it, so it propagates out of `graph.ainvoke(...)` for the
    caller (the REST router / chat tool) to translate into a `422`, same as every other
    compliance-gated pipeline in this codebase.
    """
    compliance_reviewer = ReviewCompliance()

    async def _node(state: ScenarioGraphState) -> dict[str, Any]:
        result = require_state_value(state.get("result"), "compliance", "result")
        texts = [result.narrative, *result.recommended_actions]
        texts.extend(
            evidence.detail for impact in result.impact_map for evidence in impact.evidence
        )

        compliance_result = compliance_reviewer.execute(disclaimer=result.disclaimer, texts=texts)
        if not compliance_result.passed:
            raise ComplianceViolationError(
                source=f"scenario:{result.id}", violations=compliance_result.violations
            )

        # Stamp the run's author right before persistence — this is the single point where the
        # result is written. `author_id` is `None` for preset/chat-tool runs (global) and the
        # requesting user for a free-form REST run (private), threaded in via the initial state.
        owned_result = replace(result, author_id=state.get("author_id"))
        persisted = await scenario_repository.create(owned_result)
        return {"result": persisted}

    return _node
