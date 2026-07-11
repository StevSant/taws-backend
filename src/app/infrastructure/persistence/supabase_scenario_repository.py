from app.domain.scenario.entities import ScenarioResult
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.persistence.scenario_row_mapper import scenario_from_row, scenario_to_row
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache

_SCENARIOS_TABLE = "scenarios"
_DEFAULT_RECENT_LIMIT = 20


class SupabaseScenarioRepository(ScenarioRepository):
    """ScenarioRepository adapter backed by Supabase Postgres via `supabase-py`.

    Written by the Scenario Simulation graph's Compliance step (issue #12). See migration
    `0006_scenarios.py` for the `scenarios` schema and RLS policy — mirrors `signals`'
    shape exactly (not user-owned; service-role writes bypass RLS, any authenticated user
    can read).
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def create(self, result: ScenarioResult) -> ScenarioResult:
        client = await self._clients.get()
        response = await client.table(_SCENARIOS_TABLE).insert(scenario_to_row(result)).execute()
        return scenario_from_row(response.data[0])

    async def get(self, scenario_id: str) -> ScenarioResult | None:
        client = await self._clients.get()
        response = await client.table(_SCENARIOS_TABLE).select("*").eq("id", scenario_id).execute()
        return scenario_from_row(response.data[0]) if response.data else None

    async def list_recent(self, limit: int = _DEFAULT_RECENT_LIMIT) -> list[ScenarioResult]:
        client = await self._clients.get()
        response = (
            await client.table(_SCENARIOS_TABLE)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [scenario_from_row(row) for row in response.data]
