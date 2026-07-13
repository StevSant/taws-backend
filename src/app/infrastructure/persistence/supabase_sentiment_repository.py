from functools import partial

from app.domain.sentiment.entities import SentimentReading
from app.domain.sentiment.ports import SentimentRepository
from app.infrastructure.persistence.sentiment_reading_row_mapper import (
    sentiment_reading_from_row,
    sentiment_reading_to_row,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_SENTIMENT_READINGS_TABLE = "sentiment_readings"


class SupabaseSentimentRepository(SentimentRepository):
    """SentimentRepository adapter backed by Supabase Postgres via `supabase-py` (issue #29).

    See migration `0015` for the `sentiment_readings` schema and RLS policy — mirrors
    `signals`' shape exactly (not user-owned; service-role writes bypass RLS, any
    authenticated user can read).

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

    async def create(self, reading: SentimentReading) -> SentimentReading:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SENTIMENT_READINGS_TABLE)
                .insert(sentiment_reading_to_row(reading))
                .execute()
            )
        )
        return sentiment_reading_from_row(response.data[0])

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> SentimentReading | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SENTIMENT_READINGS_TABLE)
                .select("*")
                .eq("instrument_symbol", symbol)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
        )
        return sentiment_reading_from_row(response.data[0]) if response.data else None

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        """Same two-hop select-then-delete shape (and rationale) as
        `SupabaseSignalRepository.prune_for_instrument`."""
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_SENTIMENT_READINGS_TABLE)
                .select("id")
                .eq("instrument_symbol", symbol)
                .eq("locale", locale)
                .order("created_at", desc=True)
                .execute()
            )
        )
        stale_ids = [row["id"] for row in response.data[max(keep, 0) :]]
        if not stale_ids:
            return 0
        await self._retry(
            lambda: (
                client.table(_SENTIMENT_READINGS_TABLE).delete().in_("id", stale_ids).execute()
            )
        )
        return len(stale_ids)
