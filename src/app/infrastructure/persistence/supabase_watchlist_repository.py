import uuid
from collections.abc import Sequence
from functools import partial
from typing import Any

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
        # Ordered by user-defined `position` (issue #66); NULLS LAST so never-reordered
        # lists fall back to creation order after positioned ones.
        response = await self._retry(
            lambda: (
                client.table(_WATCHLISTS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("position", desc=False, nullsfirst=False)
                .order("created_at", desc=False)
                .execute()
            )
        )
        return [watchlist_from_row(row) for row in response.data]

    async def list_all(self) -> list[Watchlist]:
        client = await self._clients.get()
        response = await self._retry(lambda: client.table(_WATCHLISTS_TABLE).select("*").execute())
        return [watchlist_from_row(row) for row in response.data]

    async def list_user_ids_tracking(self, symbols: Sequence[str]) -> set[str]:
        """Distinct owners of any watchlist containing any of `symbols` (case-insensitive).

        One PostgREST read that joins `watchlist_items` up to its parent `watchlists` via the
        `watchlist_id` FK (`select("watchlists(user_id)")`) and filters on the normalized symbol
        set. Symbols are stored uppercased (the add-item router uppercases before insert), so an
        uppercased `in_` filter is the case-insensitive match. Runs under the service-role client,
        so it sees every user's rows — the whole point of a reverse "who tracks this" lookup.
        """
        normalized = {symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()}
        if not normalized:
            return set()
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .select("watchlists(user_id)")
                .in_("symbol", list(normalized))
                .execute()
            )
        )
        user_ids: set[str] = set()
        for row in response.data:
            if isinstance(row, dict):
                user_ids.update(_extract_user_ids(row.get("watchlists")))
        return user_ids

    async def list_trackers_by_symbol(self, symbols: Sequence[str]) -> dict[str, set[str]]:
        """Per-symbol map of who tracks each symbol (see port docstring for the contract).

        One PostgREST read that selects BOTH the item's `symbol` and its parent watchlist's owner
        (`select("symbol, watchlists(user_id)")`) — the same `watchlist_items -> watchlists` FK
        embed `list_user_ids_tracking` uses, but keeping the symbol alongside each owner instead of
        flattening them all together. Filtered on the normalized (uppercased) symbol set, since
        symbols are stored uppercased by the add-item router. Runs under the service-role client so
        it sees every user's rows. Symbols nobody tracks never appear as keys.
        """
        normalized = {symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()}
        if not normalized:
            return {}
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_WATCHLIST_ITEMS_TABLE)
                .select("symbol, watchlists(user_id)")
                .in_("symbol", list(normalized))
                .execute()
            )
        )
        trackers: dict[str, set[str]] = {}
        for row in response.data:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if not isinstance(symbol, str) or not symbol.strip():
                continue
            user_ids = _extract_user_ids(row.get("watchlists"))
            if user_ids:
                trackers.setdefault(symbol.strip().upper(), set()).update(user_ids)
        return trackers

    async def list_all_tracked_symbols(self) -> set[str]:
        """Distinct uppercased symbols across every user's watchlists (see port docstring).

        One PostgREST read of the `symbol` column of `watchlist_items` across all rows — the
        service-role client bypasses RLS, so it sees every user's items, which is the whole point
        of a global "what is anyone tracking?" lookup. Symbols are stored uppercased by the
        add-item router, so the result is already canonical; `.upper()` is a cheap defensive
        normalization. Deduping happens in the set comprehension rather than via a `distinct`
        clause PostgREST doesn't expose.
        """
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_WATCHLIST_ITEMS_TABLE).select("symbol").execute()
        )
        symbols: set[str] = set()
        for row in response.data:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                symbols.add(symbol.strip().upper())
        return symbols

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

    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        client = await self._clients.get()
        # One scoped UPDATE per id: `.eq("user_id", user_id)` makes non-owned (or
        # non-existent) ids no-ops, satisfying the port's "silently ignore" contract
        # even though the service-role client bypasses RLS. Default args freeze the
        # loop variables so each lambda captures its own id/position.
        for position, watchlist_id in enumerate(ordered_ids):
            await self._retry(
                lambda wid=watchlist_id, pos=position: (
                    client.table(_WATCHLISTS_TABLE)
                    .update({"position": pos})
                    .eq("id", wid)
                    .eq("user_id", user_id)
                    .execute()
                )
            )

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


def _extract_user_ids(embedded: Any) -> list[str]:
    """Pull `user_id`s out of PostgREST's embedded `watchlists(user_id)` payload.

    A many-to-one embed (`watchlist_items -> watchlists`) normally returns a single object
    (`{"user_id": ...}`), but tolerate a list form too, so `list_user_ids_tracking` doesn't
    hinge on PostgREST's exact embed shape. Skips missing/blank ids.
    """
    if isinstance(embedded, dict):
        rows = [embedded]
    elif isinstance(embedded, list):
        rows = embedded
    else:
        return []
    return [row["user_id"] for row in rows if isinstance(row, dict) and row.get("user_id")]
