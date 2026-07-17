from functools import partial

from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.event_intelligence.ports import EventRepositoryPort
from app.infrastructure.event_intelligence.repositories.event_row_mapper import (
    enriched_event_from_row,
)
from app.infrastructure.event_intelligence.repositories.remove_postgres_null_characters import (
    remove_postgres_null_characters,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_EVENTS_TABLE = "events"


class SupabaseEventRepository(EventRepositoryPort):
    """EventRepositoryPort adapter backed by Supabase Postgres via `supabase-py`.

    See `backend/migrations/versions/0021_events.py` for the `events` schema. Events are
    shared/global market analysis, not user-owned: the pipeline writes them with the
    service-role key (bypassing RLS) and any authenticated user may read them — the same
    ownership model as `signals` and `sentiment_readings`.

    This adapter is what makes `EventRepositoryPort.get` meaningful. Its port docstring
    warns that a miss is "routine" because events "live in an in-memory store, so any
    restart drops them while the alert message (and its buttons) stays in the user's
    Telegram history forever". With a durable table behind it, a tapped inline button on an
    old alert resolves instead of dying — and a second worker can serve a callback for an
    event it never saw written.

    `save` is an upsert, not an insert: the Sentinel scan can re-encounter the same article
    across runs, and the pipeline mints a stable id per event, so re-analyzing one should
    refresh the row rather than collide with it.
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

    async def save(self, event: EnrichedEvent) -> None:
        client = await self._clients.get()
        published_at = event.original.published_at
        row = {
            "id": event.id,
            "original_title": event.original.title,
            "original_description": event.original.description,
            "original_content": event.original.content,
            "original_source": event.original.source,
            "original_url": event.original.url,
            "original_published_at": published_at.isoformat() if published_at else None,
            "summary": event.summary,
            "importance": event.importance,
            "should_notify": event.should_notify,
            "affected_assets": event.affected_assets,
            "affected_sectors": event.affected_sectors,
            "confidence": event.confidence,
            "reasoning": event.reasoning,
            "suggested_questions": event.suggested_questions,
            "analyzed_at": event.analyzed_at.isoformat(),
        }
        sanitized_row = {
            column: remove_postgres_null_characters(value) for column, value in row.items()
        }
        await self._retry(lambda: client.table(_EVENTS_TABLE).upsert(sanitized_row).execute())

    async def list_all(self) -> list[EnrichedEvent]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_EVENTS_TABLE).select("*").order("analyzed_at", desc=True).execute()
            )
        )
        return [enriched_event_from_row(row) for row in response.data]

    async def get(self, event_id: str) -> EnrichedEvent | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_EVENTS_TABLE).select("*").eq("id", event_id).execute()
        )
        return enriched_event_from_row(response.data[0]) if response.data else None
