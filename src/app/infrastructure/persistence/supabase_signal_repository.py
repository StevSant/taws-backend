import logging
from collections.abc import Sequence
from functools import partial
from typing import Any

from supabase import PostgrestAPIError

from app.domain.review.entities import ReviewedEntityType, ReviewState
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.infrastructure.persistence.build_illegal_review_transition_error import (
    build_illegal_review_transition_error,
)
from app.infrastructure.persistence.extract_stale_row_ids import extract_stale_row_ids
from app.infrastructure.persistence.review_state_row_mapper import (
    review_state_from_row,
    review_state_to_row,
)
from app.infrastructure.persistence.signal_row_mapper import (
    signal_from_row,
    signal_to_evidence_column,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_SIGNALS_TABLE = "signals"
_REVIEW_STATES_TABLE = "review_states"
_MISSING_COLUMN_CODE = "PGRST204"
_OPTIONAL_ANALYSIS_COLUMNS = {
    "analysis_available",
    "key_drivers",
    "risk_factors",
    "thesis",
}

logger = logging.getLogger(__name__)


class SupabaseSignalRepository(SignalRepository):
    """SignalRepository adapter backed by Supabase Postgres via `supabase-py`.

    Written by the Analyst agent (issue #2). See
    `backend/migrations/0001_watchlists_signals_briefings.sql` for the `signals` and
    `review_states` schema and RLS policies.

    Every `.execute()` call is wrapped in `with_supabase_retry` (issue #7), so a
    transient DNS/connectivity blip is retried a couple of times with short backoff
    before surfacing — application-level Postgrest errors are not retried, see that
    helper's docstring.
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

    async def create(self, signal: Signal) -> Signal:
        client = await self._clients.get()
        row = _signal_to_row(signal)
        try:
            response = await self._retry(lambda: client.table(_SIGNALS_TABLE).insert(row).execute())
        except PostgrestAPIError as exc:
            if not _is_missing_optional_analysis_column(exc):
                raise
            logger.warning(
                "Supabase signals schema is missing migration 0010 analysis columns; "
                "persisting the compatible core signal fields for this run."
            )
            legacy_row = {
                key: value for key, value in row.items() if key not in _OPTIONAL_ANALYSIS_COLUMNS
            }
            await self._retry(lambda: client.table(_SIGNALS_TABLE).insert(legacy_row).execute())
            return signal
        return signal_from_row(response.data[0])

    async def get(self, signal_id: str) -> Signal | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_SIGNALS_TABLE).select("*").eq("id", signal_id).execute()
        )
        return signal_from_row(response.data[0]) if response.data else None

    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        """Batch-fetch signals with one `.in_("id", [...])` query, keyed by id.

        Missing ids simply produce no row (no exception), matching the port's
        contract; empty input short-circuits without touching the network.
        """
        if not signal_ids:
            return {}
        ids = list(signal_ids)
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_SIGNALS_TABLE).select("*").in_("id", ids).execute()
        )
        signals = [signal_from_row(row) for row in response.data]
        return {signal.id: signal for signal in signals}

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SIGNALS_TABLE).select("*").eq("instrument_symbol", symbol).execute()
            )
        )
        return [signal_from_row(row) for row in response.data]

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        """Single newest row for `(symbol, locale)` — covered by the composite index
        `signals_symbol_locale_created_idx` (migration `0015`)."""
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SIGNALS_TABLE)
                .select("*")
                .eq("instrument_symbol", symbol)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        )
        return signal_from_row(response.data[0]) if response.data else None

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        """Delete all but the `keep` newest rows for `(symbol, locale)`.

        Two round trips (select the ids to drop, then delete them by id) rather than one
        `delete ... where id not in (select ... limit)`: PostgREST has no subquery syntax, and
        the alternative — a `created_at < <cutoff>` delete — would race with a concurrent
        insert of an older-timestamped row. Selecting only `id` keeps the first hop cheap even
        for a symbol with a long history, and both hops are covered by the same composite index
        as `get_latest_for_instrument`.
        """
        stale_ids = await self._stale_ids(_SIGNALS_TABLE, symbol, locale, keep)
        if not stale_ids:
            return 0
        client = await self._clients.get()
        await self._retry(
            lambda: client.table(_SIGNALS_TABLE).delete().in_("id", stale_ids).execute()
        )
        return len(stale_ids)

    async def _stale_ids(self, table: str, symbol: str, locale: str, keep: int) -> list[str]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(table)
                .select("id")
                .eq("instrument_symbol", symbol)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .execute()
            )
        )
        return extract_stale_row_ids(response.data, keep)

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        """Persist a reviewer decision, or raise `IllegalReviewTransitionError`.

        The insert is guarded by the `review_states_enforce_transition` DB trigger
        (migration `0002`) — see `build_illegal_review_transition_error` for how its
        rejection is translated into the same domain error the use-case layer's own
        (non-atomic) check raises.
        """
        client = await self._clients.get()
        try:
            response = await self._retry(
                lambda: (
                    client.table(_REVIEW_STATES_TABLE)
                    .insert(review_state_to_row(review_state))
                    .execute()
                )
            )
        except PostgrestAPIError as exc:
            translated = build_illegal_review_transition_error(exc, review_state.decision)
            if translated is not None:
                raise translated from exc
            raise
        return review_state_from_row(response.data[0])

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_REVIEW_STATES_TABLE)
                .select("*")
                .eq("entity_type", ReviewedEntityType.SIGNAL.value)
                .eq("entity_id", signal_id)
                .order("created_at")
                .execute()
            )
        )
        return [review_state_from_row(row) for row in response.data]


def _signal_to_row(signal: Signal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "instrument_symbol": signal.instrument_symbol,
        "impact_class": signal.impact_class.value,
        "confidence": signal.confidence,
        "evidence": signal_to_evidence_column(signal.evidence),
        "disclaimer": signal.disclaimer,
        "locale": signal.locale,
        "thesis": signal.thesis,
        "key_drivers": signal.key_drivers,
        "risk_factors": signal.risk_factors,
        "analysis_available": signal.analysis_available,
        "price_delta": signal.price_delta,
        "created_at": signal.created_at.isoformat(),
    }


def _is_missing_optional_analysis_column(exc: PostgrestAPIError) -> bool:
    message = exc.message or ""
    return exc.code == _MISSING_COLUMN_CODE and any(
        column in message for column in _OPTIONAL_ANALYSIS_COLUMNS
    )
