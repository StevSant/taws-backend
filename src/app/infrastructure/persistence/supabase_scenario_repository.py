from datetime import UTC, datetime
from functools import partial

from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus, ScenarioResult
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.persistence.scenario_monitor_row_mapper import (
    scenario_monitor_from_row,
    scenario_monitor_to_row,
)
from app.infrastructure.persistence.scenario_row_mapper import scenario_from_row, scenario_to_row
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_SCENARIOS_TABLE = "scenarios"
_SCENARIO_MONITORS_TABLE = "scenario_monitors"
_DEFAULT_RECENT_LIMIT = 20


class SupabaseScenarioRepository(ScenarioRepository):
    """ScenarioRepository adapter backed by Supabase Postgres via `supabase-py`.

    Written by the Scenario Simulation graph's Compliance step (issue #12). See migration
    `0006_scenarios.py` for the `scenarios` schema and RLS policy — mirrors `signals`'
    shape exactly (not user-owned; service-role writes bypass RLS, any authenticated user
    can read).

    The `scenario_monitors` methods (issue #18) below back `ScenarioMonitor` persistence —
    see migration `0008_scenario_monitors.py` for that table's schema/RLS.

    Every `.execute()` call is wrapped in `with_supabase_retry` (issue #7) — see
    `SupabaseSignalRepository`'s docstring for the shared rationale.
    """

    def __init__(
        self,
        supabase_url: str | None,
        supabase_key: str | None,
        retry_max_attempts: int = 2,
        retry_backoff_base_seconds: float = 0.2,
    ) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)
        self._retry = partial(
            with_supabase_retry,
            max_attempts=retry_max_attempts,
            backoff_base_seconds=retry_backoff_base_seconds,
        )

    async def create(self, result: ScenarioResult) -> ScenarioResult:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_SCENARIOS_TABLE).insert(scenario_to_row(result)).execute()
        )
        return scenario_from_row(response.data[0])

    async def get(self, scenario_id: str) -> ScenarioResult | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_SCENARIOS_TABLE).select("*").eq("id", scenario_id).execute()
        )
        return scenario_from_row(response.data[0]) if response.data else None

    async def list_recent(self, limit: int = _DEFAULT_RECENT_LIMIT) -> list[ScenarioResult]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIOS_TABLE)
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        )
        return [scenario_from_row(row) for row in response.data]

    async def arm_monitor(self, monitor: ScenarioMonitor) -> ScenarioMonitor:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .upsert(scenario_monitor_to_row(monitor))
                .execute()
            )
        )
        return scenario_monitor_from_row(response.data[0])

    async def get_monitor_for_user(self, scenario_id: str, user_id: str) -> ScenarioMonitor | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .select("*")
                .eq("scenario_id", scenario_id)
                .eq("user_id", user_id)
                .execute()
            )
        )
        return scenario_monitor_from_row(response.data[0]) if response.data else None

    async def list_armed_monitors(self) -> list[ScenarioMonitor]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .select("*")
                .eq("status", ScenarioMonitorStatus.ARMED.value)
                .execute()
            )
        )
        return [scenario_monitor_from_row(row) for row in response.data]

    async def mark_monitor_matched(self, monitor_id: str, match_reason: str) -> ScenarioMonitor:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .update(
                    {
                        "status": ScenarioMonitorStatus.MATCHED.value,
                        "matched_at": datetime.now(UTC).isoformat(),
                        "match_reason": match_reason,
                    }
                )
                .eq("id", monitor_id)
                .execute()
            )
        )
        return scenario_monitor_from_row(response.data[0])

    async def mark_monitor_expired(self, monitor_id: str) -> ScenarioMonitor:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .update({"status": ScenarioMonitorStatus.EXPIRED.value})
                .eq("id", monitor_id)
                .execute()
            )
        )
        return scenario_monitor_from_row(response.data[0])

    async def disarm_monitor(self, scenario_id: str, user_id: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .delete()
                .eq("scenario_id", scenario_id)
                .eq("user_id", user_id)
                .execute()
            )
        )
