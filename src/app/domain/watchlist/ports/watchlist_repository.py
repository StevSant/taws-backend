from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.domain.watchlist.entities import Watchlist, WatchlistItem


class WatchlistRepository(ABC):
    """Port for persisting watchlists and their items, scoped to the owning user."""

    @abstractmethod
    async def create(self, watchlist: Watchlist) -> Watchlist:
        """Create a new watchlist and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, watchlist_id: str) -> Watchlist | None:
        """Return the watchlist with this id, or `None` if it doesn't exist."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        """Return every watchlist owned by `user_id`."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[Watchlist]:
        """Return every watchlist across every user.

        Used by the Watchdog/Notifier agent's global scheduled scan and daily briefing run
        (issue #10), neither of which has a single request-bound user to scope to — unlike
        `list_for_user`, which backs the per-user watchlist API.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_user_ids_tracking(self, symbols: Sequence[str]) -> set[str]:
        """Return the distinct `user_id`s who track ANY of `symbols` in ANY of their watchlists.

        The reverse of `list_items` (watchlist -> symbols): given a set of symbols, find every
        user who has at least one of them on at least one watchlist. Backs the Sentinel scan's
        watchlist-targeted delivery path (`BroadcastImportantEvents`), which routes a
        mid-importance event only to users who actually track one of its affected assets, rather
        than broadcasting it market-wide.

        Matching is case-insensitive; an empty or all-blank `symbols` yields an empty set (no
        symbols means nobody to notify — never "everybody"). Returns a set, so a user tracking
        several of the symbols is counted once.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_trackers_by_symbol(self, symbols: Sequence[str]) -> dict[str, set[str]]:
        """Map each of `symbols` to the distinct `user_id`s who track it, keyed by canonical
        UPPERCASE symbol.

        The per-symbol breakdown of `list_user_ids_tracking`: where that method collapses "who
        tracks ANY of these symbols" into one flat set, this keeps the symbol -> user_ids
        association intact. Backs the Sentinel scan's PERSONALIZED watchlist-targeted delivery
        (`BroadcastImportantEvents`), which inverts it to `user_id -> {matched symbols}` so a
        targeted alert can tell each user WHICH of their tracked assets the event affects — not
        just that one of them did.

        Only symbols that at least one user tracks appear as keys; a symbol nobody tracks is
        omitted entirely (never mapped to an empty set). Matching is case-insensitive and an
        empty or all-blank `symbols` yields an empty dict (no symbols means nobody to notify —
        never "everybody"). The union of all the value sets equals `list_user_ids_tracking` for
        the same input.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_all_tracked_symbols(self) -> set[str]:
        """Return the distinct set of symbols tracked across ALL users' watchlists, uppercased.

        The symbol-space complement of `list_all` (which returns whole watchlists) and of
        `list_user_ids_tracking` (symbols -> users): this collapses every item on every user's
        watchlists into one deduplicated, uppercased set. Backs the Sentinel scan's cheap
        relevance pre-gate (`BroadcastImportantEvents`), which builds a match vocabulary from this
        set (plus each symbol's company name and the macro keyword list) once per scan to drop
        obviously off-topic articles before spending any LLM call. Returns an empty set when no
        user tracks anything.
        """
        raise NotImplementedError

    @abstractmethod
    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        """Rename an existing watchlist and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        """Persist a new display order for `user_id`'s watchlists (issue #66).

        Sets `position = index` for each id in `ordered_ids`, in list order. Only rows
        owned by `user_id` are touched — ids that don't belong to the caller (or don't
        exist) are silently ignored, never raising and never affecting another user's
        rows. Ids the user owns but omits from the list keep their current `position`.
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, watchlist_id: str) -> None:
        """Delete a watchlist and cascade-delete its items."""
        raise NotImplementedError

    @abstractmethod
    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        """Return every item (tracked instrument) in a watchlist."""
        raise NotImplementedError

    @abstractmethod
    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        """Add an instrument (by symbol) to a watchlist and return the created item."""
        raise NotImplementedError

    @abstractmethod
    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        """Remove a single item from a watchlist."""
        raise NotImplementedError
