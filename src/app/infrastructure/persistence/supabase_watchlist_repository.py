import uuid
from functools import partial

from supabase import PostgrestAPIError

from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.persistence.build_watchlist_persistence_error import (
    build_watchlist_persistence_error,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.watchlist_item_row_mapper import watchlist_item_from_row
from app.infrastructure.persistence.watchlist_row_mapper import watchlist_from_row
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_WATCHLISTS_TABLE = "watchlists"
_WATCHLIST_ITEMS_TABLE = "watchlist_items"


class SupabaseWatchlistRepository(WatchlistRepository):
    """WatchlistRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `backend/migrations/0001_watchlists_signals_briefings.sql` for the schema
    (`watchlists`, `watchlist_items`) and their RLS policies (scoped to `auth.uid()`).

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

    async def create(self, watchlist: Watchlist) -> Watchlist:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLISTS_TABLE)
                .insert(
                    {
                        "id": watchlist.id,
                        "user_id": watchlist.user_id,
                        "name": watchlist.name,
                        "created_at": watchlist.created_at.isoformat(),
                    }
                )
                .execute()
            )
        )
        return watchlist_from_row(response.data[0])

    async def get(self, watchlist_id: str) -> Watchlist | None:
        """Return the watchlist, or raise `InvalidWatchlistIdentifierError` on a bad id.

        A malformed (non-uuid) `watchlist_id` is rejected by Postgres with `22P02`; this
        is the single read every by-id endpoint funnels through, so translating it here
        gives all of them a 422 instead of a generic 500.
        """
        client = await self._clients.get()
        try:
            response = await self._retry(
                lambda: client.table(_WATCHLISTS_TABLE).select("*").eq("id", watchlist_id).execute()
            )
        except PostgrestAPIError as exc:
            translated = build_watchlist_persistence_error(exc)
            if translated is not None:
                raise translated from exc
            raise
        return watchlist_from_row(response.data[0]) if response.data else None

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_WATCHLISTS_TABLE).select("*").eq("user_id", user_id).execute()
        )
        return [watchlist_from_row(row) for row in response.data]

    async def list_all(self) -> list[Watchlist]:
        client = await self._clients.get()
        response = await self._retry(lambda: client.table(_WATCHLISTS_TABLE).select("*").execute())
        return [watchlist_from_row(row) for row in response.data]

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLISTS_TABLE)
                .update({"name": name})
                .eq("id", watchlist_id)
                .execute()
            )
        )
        return watchlist_from_row(response.data[0])

    async def delete(self, watchlist_id: str) -> None:
        client = await self._clients.get()
        # `watchlist_items` FKs `ON DELETE CASCADE` — no need to delete items here.
        await self._retry(
            lambda: client.table(_WATCHLISTS_TABLE).delete().eq("id", watchlist_id).execute()
        )

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .select("*")
                .eq("watchlist_id", watchlist_id)
                .execute()
            )
        )
        return [watchlist_item_from_row(row) for row in response.data]

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        """Add a symbol, or raise `DuplicateWatchlistItemError` if already tracked.

        A repeat symbol trips the `unique (watchlist_id, symbol)` constraint (`23505`);
        a malformed `watchlist_id` trips `22P02` — both translated to domain errors so
        the router maps them to 409 / 422 instead of a generic 500.
        """
        client = await self._clients.get()
        try:
            response = await self._retry(
                lambda: (
                    client.table(_WATCHLIST_ITEMS_TABLE)
                    .insert(
                        {"id": str(uuid.uuid4()), "watchlist_id": watchlist_id, "symbol": symbol}
                    )
                    .execute()
                )
            )
        except PostgrestAPIError as exc:
            translated = build_watchlist_persistence_error(exc, symbol=symbol)
            if translated is not None:
                raise translated from exc
            raise
        return watchlist_item_from_row(response.data[0])

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        client = await self._clients.get()
        try:
            await self._retry(
                lambda: (
                    client.table(_WATCHLIST_ITEMS_TABLE)
                    .delete()
                    .eq("watchlist_id", watchlist_id)
                    .eq("id", item_id)
                    .execute()
                )
            )
        except PostgrestAPIError as exc:
            translated = build_watchlist_persistence_error(exc)
            if translated is not None:
                raise translated from exc
            raise
