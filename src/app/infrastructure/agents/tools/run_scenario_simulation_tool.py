from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.compliance import ComplianceViolationError
from app.application.scenario import InvalidScenarioIntakeError, UnknownPresetError
from app.domain.scenario.entities import ScenarioResult
from app.infrastructure.agents.scenario import ScenarioSimulationRunner


class _RunScenarioSimulationArgs(BaseModel):
    preset_id: str | None = Field(
        default=None,
        description=(
            "A curated preset scenario id, e.g. 'fed-hike-50bp', 'btc-etf-rejected', "
            "'nvda-earnings-miss', 'oil-supply-shock'. Prefer this when the user's request "
            "clearly matches a known preset; leave unset and use free_text otherwise."
        ),
    )
    free_text: str | None = Field(
        default=None,
        description=(
            "A free-form 'what if' market scenario description, e.g. 'What if the Fed cuts "
            "rates by 100bp next quarter?'. Only used when preset_id is not set."
        ),
    )


def build_run_scenario_simulation_tool(
    scenario_simulation_runner: ScenarioSimulationRunner,
    default_locale: str,
) -> StructuredTool:
    """Build a LangChain tool wrapping the full Scenario Simulation graph (issue #12) for
    the `advisor` specialist — thin wrapper, same shape as
    `generate_consequence_chain_tool.py`.

    This is how "reachable via chat" is satisfied without forcing the graph's six steps
    through individual chat turns: one tool call runs Intake -> Context gathering ->
    Causal chain -> Quantification -> Synthesis -> Compliance end to end and returns the
    persisted, synthesized `ScenarioResult`. Bound to `advisor` (not a new specialist
    route — see `scenario_graph.py`'s docstring): the Advisor persona already composes
    cross-specialist summaries and points the user toward what to research next, which is
    exactly a `ScenarioResult`'s shape (impact map + recommended research actions).

    Catches `ComplianceViolationError`/`UnknownPresetError`/`InvalidScenarioIntakeError`
    and returns a plain-text explanation instead of letting the tool call raise — a chat
    tool result must always be a string the model can read back to the user, unlike the
    REST endpoint, which is expected to translate these into HTTP status codes.
    """

    async def _run(preset_id: str | None = None, free_text: str | None = None) -> str:
        try:
            result = await scenario_simulation_runner.execute(
                preset_id=preset_id, free_text=free_text, locale=default_locale
            )
        except InvalidScenarioIntakeError as exc:
            return str(exc)
        except UnknownPresetError as exc:
            return str(exc)
        except ComplianceViolationError as exc:
            return f"Scenario simulation failed compliance review: {exc}"
        return _format_result(result)

    return StructuredTool.from_function(
        coroutine=_run,
        name="run_scenario_simulation",
        description=(
            "Run the full Scenario Lab simulation for a 'what if' market scenario — either "
            "a curated preset id or free-form text — and return a structured impact "
            "assessment (per-asset-class direction, confidence, and cited evidence) plus "
            "recommended research actions. Always call this instead of reasoning about a "
            "hypothetical scenario's market impact from memory alone."
        ),
        args_schema=_RunScenarioSimulationArgs,
    )


def _format_result(result: ScenarioResult) -> str:
    lines = [
        f"Scenario: {result.title}",
        result.narrative,
        "",
        "Impact map:",
    ]
    for impact in result.impact_map:
        lines.append(
            f"- {impact.asset_class.value}: {impact.direction.value} "
            f"(confidence={impact.confidence:.2f})"
        )
        lines.extend(f"    {evidence.detail}" for evidence in impact.evidence)
    if result.recommended_actions:
        lines.append("")
        lines.append("Recommended research actions:")
        lines.extend(f"- {action}" for action in result.recommended_actions)
    lines.append("")
    lines.append(result.disclaimer)
    return "\n".join(lines)
