from typing import Any

from app.infrastructure.realtime.tools.args import GetWatchlistArgs


async def handle_get_watchlist(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Return the caller's own watchlists and the instruments tracked in each.

    Delegates to `WatchlistRepository.list_for_user` / `list_items`. SECURITY: the list is
    scoped strictly by `user_id`, which comes from the verified JWT (threaded through
    `dispatch_realtime_tool`) — it is NEVER taken from the model-supplied arguments, so a
    voice call can only ever read the authenticated user's own watchlists. Each watchlist is
    flattened to name + tracked symbols, the shape the voice model narrates.
    """
    _: GetWatchlistArgs = args
    repository = container.get_watchlist_repository()
    watchlists = await repository.list_for_user(user_id)

    entries = []
    for watchlist in watchlists:
        items = await repository.list_items(watchlist.id)
        entries.append(
            {
                "id": watchlist.id,
                "name": watchlist.name,
                "symbols": [item.symbol for item in items],
            }
        )

    return {"count": len(entries), "watchlists": entries}
