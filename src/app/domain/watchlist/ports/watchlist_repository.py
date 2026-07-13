from abc import ABC, abstractmethod

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
