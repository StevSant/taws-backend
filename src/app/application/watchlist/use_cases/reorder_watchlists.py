from app.domain.watchlist.ports import WatchlistRepository


class ReorderWatchlists:
    """Persist a user-chosen display order for their watchlists (issue #66).

    Thin orchestration over `WatchlistRepository.reorder`: the ownership scoping and
    silent-ignore-of-unowned-ids semantics live in the adapter (see the port's docstring).
    Kept as an application use case so the router depends on the injected port, not on the
    Supabase adapter directly.
    """

    def __init__(self, watchlist_repository: WatchlistRepository) -> None:
        self._watchlist_repository = watchlist_repository

    async def execute(self, user_id: str, ordered_ids: list[str]) -> None:
        await self._watchlist_repository.reorder(user_id, ordered_ids)
