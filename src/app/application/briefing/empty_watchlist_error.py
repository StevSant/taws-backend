class EmptyWatchlistError(RuntimeError):
    """Raised when a briefing is requested for a watchlist that tracks no instruments yet."""

    def __init__(self, watchlist_id: str) -> None:
        super().__init__(f"Watchlist {watchlist_id!r} has no tracked instruments")
        self.watchlist_id = watchlist_id
