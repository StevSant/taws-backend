import uuid

from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.watchlist_item_row_mapper import watchlist_item_from_row
from app.infrastructure.persistence.watchlist_row_mapper import watchlist_from_row

_WATCHLISTS_TABLE = "watchlists"
_WATCHLIST_ITEMS_TABLE = "watchlist_items"


class SupabaseWatchlistRepository(WatchlistRepository):
    """WatchlistRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `backend/migrations/0001_watchlists_signals_briefings.sql` for the schema
    (`watchlists`, `watchlist_items`) and their RLS policies (scoped to `auth.uid()`).
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def create(self, watchlist: Watchlist) -> Watchlist:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLISTS_TABLE)
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
        return watchlist_from_row(response.data[0])

    async def get(self, watchlist_id: str) -> Watchlist | None:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLISTS_TABLE).select("*").eq("id", watchlist_id).execute()
        )
        return watchlist_from_row(response.data[0]) if response.data else None

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLISTS_TABLE).select("*").eq("user_id", user_id).execute()
        )
        return [watchlist_from_row(row) for row in response.data]

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLISTS_TABLE)
            .update({"name": name})
            .eq("id", watchlist_id)
            .execute()
        )
        return watchlist_from_row(response.data[0])

    async def delete(self, watchlist_id: str) -> None:
        client = await self._clients.get()
        # `watchlist_items` FKs `ON DELETE CASCADE` — no need to delete items here.
        await client.table(_WATCHLISTS_TABLE).delete().eq("id", watchlist_id).execute()

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLIST_ITEMS_TABLE)
            .select("*")
            .eq("watchlist_id", watchlist_id)
            .execute()
        )
        return [watchlist_item_from_row(row) for row in response.data]

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        client = await self._clients.get()
        response = (
            await client.table(_WATCHLIST_ITEMS_TABLE)
            .insert({"id": str(uuid.uuid4()), "watchlist_id": watchlist_id, "symbol": symbol})
            .execute()
        )
        return watchlist_item_from_row(response.data[0])

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        client = await self._clients.get()
        await (
            client.table(_WATCHLIST_ITEMS_TABLE)
            .delete()
            .eq("watchlist_id", watchlist_id)
            .eq("id", item_id)
            .execute()
        )
