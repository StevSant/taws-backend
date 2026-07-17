import logging
from typing import Any, cast

from app.application.scenario import InvalidScenarioIntakeError
from app.domain.freshness import FreshnessPolicy
from app.domain.scenario.entities import ScenarioResult
from app.domain.scenario.ports import ScenarioRepository

logger = logging.getLogger(__name__)


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

    Freshness gate (issue #29): the gate lives HERE rather than in an application-layer
    wrapper because this class is the only entry point to the scenario pipeline — the graph
    persists the result from inside its own Compliance node, so there is no application-layer
    seam between "run" and "persist" to gate at. It depends only on domain types
    (`ScenarioRepository`, `FreshnessPolicy`), so no layering rule is bent: infrastructure
    depending inward on domain is exactly the intended direction.
    """

    def __init__(
        self,
        graph: Any,
        scenario_repository: ScenarioRepository,
        freshness_policy: FreshnessPolicy,
        retention_keep: int,
    ) -> None:
        self._graph = graph
        self._scenario_repository = scenario_repository
        self._freshness_policy = freshness_policy
        self._retention_keep = retention_keep

    async def execute(
        self,
        *,
        preset_id: str | None = None,
        free_text: str | None = None,
        locale: str,
        user_id: str | None = None,
        force: bool = False,
    ) -> ScenarioResult:
        """Run one scenario end to end and return its persisted `ScenarioResult`.

        `locale` is required (no built-in default): every caller (REST router, chat
        tool, Telegram `/simular` handler) resolves its own fallback from
        `Settings.default_locale` before calling this, so a default locale is never
        hardcoded here.

        Cached per `(preset_id, locale)` when a preset is used and the last result is still
        within the default TTL (a scenario isn't about one instrument, so there is no asset
        class to key a TTL on — `FreshnessPolicy` falls back to `default_ttl`). FREE-FORM runs
        are never cached: two users' free text is never byte-identical, so there is no stable
        key to cache under, and pretending otherwise would risk serving one user's answer to
        another user's different question. `force` bypasses the gate (internal use only, same
        rationale as `GenerateSignal.execute`).

        `user_id` scopes a FREE-FORM run to its author (migration 0025): the resulting
        `ScenarioResult.author_id` is set to it so the run stays private to that user. Preset
        runs ignore it (they're global, `author_id = None`), as does the chat-tool path, which
        passes no `user_id`.

        Raises `InvalidScenarioIntakeError` if neither `preset_id` nor `free_text` is
        given, `UnknownPresetError` for an unrecognized `preset_id`, and
        `ComplianceViolationError` if the synthesized result fails the Compliance step —
        all raised from inside graph nodes and left to propagate out of `ainvoke(...)`
        uncaught, for the caller (router / chat tool) to translate.
        """
        if not preset_id and not (free_text and free_text.strip()):
            raise InvalidScenarioIntakeError

        if preset_id and not force:
            cached = await self._latest_for_preset(preset_id, locale)
            if cached is not None and self._freshness_policy.is_fresh(cached.created_at):
                logger.info(
                    "Scenario preset %s (%s) served from cache; skipping the pipeline.",
                    preset_id,
                    locale,
                )
                return cached

        # Preset runs are global research (no owner); a free-form run belongs to the user
        # who typed it. `user_id` is None on the chat-tool path, which keeps those global too.
        author_id = None if preset_id else user_id
        final_state = await self._graph.ainvoke(
            {
                "preset_id": preset_id,
                "free_text": free_text,
                "locale": locale,
                "author_id": author_id,
            }
        )
        result = final_state.get("result")
        if result is None:
            # Should be unreachable: the Compliance node either raises or returns a
            # `result`. Guarded anyway so a future graph-wiring change fails loudly
            # instead of silently returning `None` to a caller expecting a `ScenarioResult`.
            raise RuntimeError("Scenario simulation graph completed without producing a result.")

        if preset_id:
            await self._prune(preset_id, locale)
        return cast(ScenarioResult, result)

    async def _latest_for_preset(self, preset_id: str, locale: str) -> ScenarioResult | None:
        """Cache lookup; a store blip degrades to "no cache" (rerun) rather than raising —
        same guard as `GenerateSignal._latest_signal`."""
        try:
            return await self._scenario_repository.get_latest_for_preset(preset_id, locale)
        except Exception:
            logger.warning(
                "Scenario cache lookup failed for preset %s (%s); rerunning.",
                preset_id,
                locale,
                exc_info=True,
            )
            return None

    async def _prune(self, preset_id: str, locale: str) -> None:
        """Best-effort retention: never fail a completed run because cleanup of OLD rows
        failed — same rationale as `GenerateSignal._prune`."""
        try:
            deleted = await self._scenario_repository.prune_for_preset(
                preset_id, locale, self._retention_keep
            )
        except Exception:
            logger.warning(
                "Scenario retention prune failed for preset %s (%s).",
                preset_id,
                locale,
                exc_info=True,
            )
            return
        if deleted:
            logger.info(
                "Pruned %d stale scenario(s) for preset %s (%s).", deleted, preset_id, locale
            )
