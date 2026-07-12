from functools import partial

from supabase import PostgrestAPIError

from app.domain.review.entities import ReviewedEntityType, ReviewState
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.infrastructure.persistence.build_illegal_review_transition_error import (
    build_illegal_review_transition_error,
)
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
        response = await self._retry(
            lambda: (
                client.table(_SIGNALS_TABLE)
                .insert(
                    {
                        "id": signal.id,
                        "instrument_symbol": signal.instrument_symbol,
                        "impact_class": signal.impact_class.value,
                        "confidence": signal.confidence,
                        "evidence": signal_to_evidence_column(signal.evidence),
                        "disclaimer": signal.disclaimer,
                        "price_delta": signal.price_delta,
                        "created_at": signal.created_at.isoformat(),
                    }
                )
                .execute()
            )
        )
        return signal_from_row(response.data[0])

    async def get(self, signal_id: str) -> Signal | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_SIGNALS_TABLE).select("*").eq("id", signal_id).execute()
        )
        return signal_from_row(response.data[0]) if response.data else None

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SIGNALS_TABLE).select("*").eq("instrument_symbol", symbol).execute()
            )
        )
        return [signal_from_row(row) for row in response.data]

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
