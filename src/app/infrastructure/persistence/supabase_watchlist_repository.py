import uuid
from functools import partial

from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
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
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_WATCHLISTS_TABLE).select("*").eq("id", watchlist_id).execute()
        )
        return watchlist_from_row(response.data[0]) if response.data else None

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        """List every watchlist owned by `user_id`, ordered by `created_at` (MEDIUM
        fix, post-hoc adversarial review): without a stable `.order(...)` clause,
        row order is whatever Postgres/PostgREST happens to return, which makes
        the router's `existing[0]` (`_resolve_owned_watchlist_id`'s "the caller's
        default watchlist") non-deterministic across requests.
        """
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLISTS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("created_at")
                .execute()
            )
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
        """Add `symbol` to `watchlist_id`, idempotent on `(watchlist_id, symbol)` (FIX #4).

        Upserts with `on_conflict="watchlist_id,symbol"` + `ignore_duplicates=True`
        instead of a plain insert, so re-registering an already-tracked symbol (e.g.
        via `RegisterInstrument`) is a true no-op: no duplicate row, no error. A
        no-op conflict can leave `.upsert(...).execute()`'s own response empty/stale
        for that row, so the row is re-selected by `(watchlist_id, symbol)` before
        mapping — this keeps the return type a real `WatchlistItem` either way.
        """
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .upsert(
                    {"id": str(uuid.uuid4()), "watchlist_id": watchlist_id, "symbol": symbol},
                    on_conflict="watchlist_id,symbol",
                    ignore_duplicates=True,
                )
                .execute()
            )
        )
        response = await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .select("*")
                .eq("watchlist_id", watchlist_id)
                .eq("symbol", symbol)
                .execute()
            )
        )
        if not response.data:
            # LOW fix (post-hoc adversarial review): an empty re-select (stale
            # read / RLS mismatch) must raise a clear, greppable error instead of
            # `IndexError`-ing on `response.data[0]`, which would otherwise
            # surface as an opaque 500 with no indication of which table/row.
            raise LookupError(
                f"watchlist_items row not found after upsert for "
                f"watchlist_id={watchlist_id!r}, symbol={symbol!r}"
            )
        return watchlist_item_from_row(response.data[0])

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .delete()
                .eq("watchlist_id", watchlist_id)
                .eq("id", item_id)
                .execute()
            )
        )
