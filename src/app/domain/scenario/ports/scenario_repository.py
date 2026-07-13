from abc import ABC, abstractmethod

from app.domain.scenario.entities import ScenarioMonitor, ScenarioResult

_DEFAULT_RECENT_LIMIT = 20


class ScenarioRepository(ABC):
    """Port for persisting Scenario Simulation runs (issue #12) AND armed Scenario
    Monitors (issue #18) — monitors are kept on this same port rather than a separate one
    because they're purely a lifecycle/annotation on top of an existing `ScenarioResult`
    (no monitor can exist without a scenario, and there's no independent monitor query
    shape that would justify its own port/adapter pair). See `ScenarioMonitor`'s docstring
    for the entity shape.

    `ScenarioResult`s are NOT user-owned: a "Fed +50bp" scenario run is shared/global
    research (a preset run has no single owner, and even a free-form run is scenario
    analysis about the market, not private data about the user who typed it) — same
    visibility model as `SignalRepository`, not `WatchlistRepository`. See
    `infrastructure/persistence/supabase_scenario_repository.py` and migration `0004` for
    the concrete RLS shape this implies (mirrors `signals`' read-only-for-authenticated
    policy). Monitors themselves ARE user-owned (who armed it), same shape as `Watchlist`.
    """

    @abstractmethod
    async def create(self, result: ScenarioResult) -> ScenarioResult:
        """Create a new scenario result and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, scenario_id: str) -> ScenarioResult | None:
        """Return the scenario result with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_recent(self, limit: int = _DEFAULT_RECENT_LIMIT) -> list[ScenarioResult]:
        """Return the most recently generated scenario results, most-recent first.

        Backs a basic Scenario Lab history view (`GET /api/v1/scenarios`) — not in the
        issue's explicit acceptance criteria, but needed for any "basic UI" to show past
        runs without the client tracking every generated id itself.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_latest_for_preset(self, preset_id: str, locale: str) -> ScenarioResult | None:
        """Return the newest result for `(preset_id, locale)`, or `None` if there is none.

        The freshness-cache lookup for PRESET scenario runs (issue #29). Free-form runs are
        deliberately not covered: they have no stable key to cache under (two users' free
        text is never identical), so `ScenarioSimulationRunner` only consults this when a
        `preset_id` was supplied. `locale` is part of the key — see `ScenarioResult.locale`.
        """
        raise NotImplementedError

    @abstractmethod
    async def prune_for_preset(self, preset_id: str, locale: str, keep: int) -> int:
        """Delete all but the `keep` newest results for `(preset_id, locale)`; return how
        many rows were deleted. Retention counterpart of
        `SignalRepository.prune_for_instrument` — same bounded-growth rationale."""
        raise NotImplementedError

    @abstractmethod
    async def arm_monitor(self, monitor: ScenarioMonitor) -> ScenarioMonitor:
        """Create or replace (upsert by `id`) an armed `ScenarioMonitor` row.

        `ArmScenarioMonitor` decides whether to reuse an existing monitor's id (re-arming)
        or mint a new one — this method just persists whatever it's handed."""
        raise NotImplementedError

    @abstractmethod
    async def get_monitor_for_user(self, scenario_id: str, user_id: str) -> ScenarioMonitor | None:
        """Return this user's existing monitor for this scenario (any status), or `None`.

        Used by `ArmScenarioMonitor` to decide create-vs-reset, and by the disarm endpoint
        to check ownership before deleting."""
        raise NotImplementedError

    @abstractmethod
    async def list_armed_monitors(self) -> list[ScenarioMonitor]:
        """Return every monitor currently in `ARMED` status, across every user.

        Global (not user-scoped), same shape as `WatchlistRepository.list_all` — backs
        Watchdog's scheduled `EvaluateScenarioMonitors` pass, which has no single
        request-bound user to scope to."""
        raise NotImplementedError

    @abstractmethod
    async def mark_monitor_matched(self, monitor_id: str, match_reason: str) -> ScenarioMonitor:
        """Transition a monitor to `MATCHED`, recording `match_reason` and `matched_at`
        (now). See `ScenarioMonitor`'s docstring for why this doesn't delete the row."""
        raise NotImplementedError

    @abstractmethod
    async def mark_monitor_expired(self, monitor_id: str) -> ScenarioMonitor:
        """Transition a monitor to `EXPIRED` (its TTL elapsed with no match)."""
        raise NotImplementedError

    @abstractmethod
    async def disarm_monitor(self, scenario_id: str, user_id: str) -> None:
        """Delete this user's monitor for this scenario, if any. No-op if none exists —
        disarming something that isn't armed is not an error."""
        raise NotImplementedError
