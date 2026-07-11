from typing import Any, cast

from app.application.scenario import InvalidScenarioIntakeError
from app.domain.scenario.entities import ScenarioResult


class ScenarioSimulationRunner:
    """Thin adapter wrapping the compiled Scenario Simulation graph behind a plain
    `execute(...)` method — same "hide `.ainvoke`/state-dict mechanics behind a clean
    method" role `LangGraphAgentRunner` plays for the chat graph, just for a single-shot
    pipeline instead of a streamed conversational turn.

    Not a domain port: unlike `AgentRunner`, there is exactly one plausible adapter for
    "run this specific compiled LangGraph" (LangGraph itself), so a port/adapter split
    here would add indirection with no real swap point — same reasoning
    `GenerateConsequenceChain`/`ComputeMarketStats` follow for not being behind ports of
    their own. Built and cached once by `Container.get_scenario_simulation_runner`, and
    used identically by `POST /api/v1/scenarios/generate` and the
    `run_scenario_simulation` chat tool.
    """

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def execute(
        self, *, preset_id: str | None = None, free_text: str | None = None, locale: str
    ) -> ScenarioResult:
        """Run one scenario end to end and return its persisted `ScenarioResult`.

        `locale` is required (no built-in default): every caller (REST router, chat
        tool, Telegram `/simular` handler) resolves its own fallback from
        `Settings.default_locale` before calling this, so a default locale is never
        hardcoded here.

        Raises `InvalidScenarioIntakeError` if neither `preset_id` nor `free_text` is
        given, `UnknownPresetError` for an unrecognized `preset_id`, and
        `ComplianceViolationError` if the synthesized result fails the Compliance step —
        all raised from inside graph nodes and left to propagate out of `ainvoke(...)`
        uncaught, for the caller (router / chat tool) to translate.
        """
        if not preset_id and not (free_text and free_text.strip()):
            raise InvalidScenarioIntakeError

        final_state = await self._graph.ainvoke(
            {"preset_id": preset_id, "free_text": free_text, "locale": locale}
        )
        result = final_state.get("result")
        if result is None:
            # Should be unreachable: the Compliance node either raises or returns a
            # `result`. Guarded anyway so a future graph-wiring change fails loudly
            # instead of silently returning `None` to a caller expecting a `ScenarioResult`.
            raise RuntimeError("Scenario simulation graph completed without producing a result.")
        return cast(ScenarioResult, result)
