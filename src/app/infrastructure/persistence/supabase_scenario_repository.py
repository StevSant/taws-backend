from datetime import UTC, datetime
from functools import partial

from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus, ScenarioResult
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.persistence.extract_stale_row_ids import extract_stale_row_ids
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
    `0006_scenarios.py` for the base `scenarios` schema and `0025_scenario_author.py` for the
    `author_id` visibility split: service-role writes bypass RLS, and reads are scoped in
    `list_recent`/the router — global rows (`author_id is null`: presets, chat-tool runs) are
    readable by anyone, while a free-form run is private to its author.

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

    async def list_recent(
        self, user_id: str, limit: int = _DEFAULT_RECENT_LIMIT
    ) -> list[ScenarioResult]:
        """Global rows (`author_id is null`) UNION this user's own free-form rows, most
        recent first. Two parametric queries merged in-process rather than one `.or_()`
        string: `user_id` comes from a JWT that is only signature-verified in production
        (dev-fallback reads it unverified), so it must never be interpolated into a raw
        PostgREST filter expression — `.is_`/`.eq` bind it as a value instead."""
        client = await self._clients.get()
        global_response = await self._retry(
            lambda: (
                client.table(_SCENARIOS_TABLE)
                .select("*")
                .is_("author_id", "null")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        )
        own_response = await self._retry(
            lambda: (
                client.table(_SCENARIOS_TABLE)
                .select("*")
                .eq("author_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
        )
        results = [scenario_from_row(row) for row in [*global_response.data, *own_response.data]]
        merged = {result.id: result for result in results}
        ordered = sorted(merged.values(), key=lambda result: result.created_at, reverse=True)
        return ordered[:limit]

    async def get_latest_for_preset(self, preset_id: str, locale: str) -> ScenarioResult | None:
        """Single newest row for `(preset_id, locale)` — covered by the composite index
        `scenarios_preset_locale_created_idx` (migration `0015`)."""
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIOS_TABLE)
                .select("*")
                .eq("preset_id", preset_id)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        )
        return scenario_from_row(response.data[0]) if response.data else None

    async def prune_for_preset(self, preset_id: str, locale: str, keep: int) -> int:
        """Delete all but the `keep` newest rows for `(preset_id, locale)`. Same two-hop
        select-then-delete shape (and rationale) as
        `SupabaseSignalRepository.prune_for_instrument`."""
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIOS_TABLE)
                .select("id")
                .eq("preset_id", preset_id)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .execute()
            )
        )
        stale_ids = extract_stale_row_ids(response.data, keep)
        if not stale_ids:
            return 0
        await self._retry(
            lambda: client.table(_SCENARIOS_TABLE).delete().in_("id", stale_ids).execute()
        )
        return len(stale_ids)

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

    async def list_monitors_for_user(self, user_id: str) -> list[ScenarioMonitor]:
        """Every monitor owned by `user_id`, any status, newest-armed first — covered by the
        `scenario_monitors_user_id_idx` index (migration 0008). `user_id` is bound as a value
        via `.eq` (never interpolated into a raw filter), same JWT-safety rule `list_recent`
        follows."""
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SCENARIO_MONITORS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("armed_at", desc=True)
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
