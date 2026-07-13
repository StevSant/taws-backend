class DuplicateWatchlistItemError(Exception):
    """Raised when a symbol already tracked in a watchlist is added again.

    The `watchlist_items` table has a `unique (watchlist_id, symbol)` constraint
    (migration `0001_watchlists_signals_briefings.py`). A second insert of the same
    symbol is rejected by Postgres with `errcode = '23505'` (unique_violation), which
    `SupabaseWatchlistRepository.add_item` translates into this domain error so the
    router never sees a raw Postgres code. Caught by the API layer and mapped to
    `409 Conflict`.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"'{symbol}' is already in this watchlist")
