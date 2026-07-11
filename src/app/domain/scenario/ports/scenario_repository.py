from abc import ABC, abstractmethod

from app.domain.scenario.entities import ScenarioResult

_DEFAULT_RECENT_LIMIT = 20


class ScenarioRepository(ABC):
    """Port for persisting Scenario Simulation runs (issue #12).

    `ScenarioResult`s are NOT user-owned: a "Fed +50bp" scenario run is shared/global
    research (a preset run has no single owner, and even a free-form run is scenario
    analysis about the market, not private data about the user who typed it) — same
    visibility model as `SignalRepository`, not `WatchlistRepository`. See
    `infrastructure/persistence/supabase_scenario_repository.py` and migration `0004` for
    the concrete RLS shape this implies (mirrors `signals`' read-only-for-authenticated
    policy).
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
