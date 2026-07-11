from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class WatchlistItem:
    """A single instrument tracked inside a `Watchlist` (by symbol, not FK to `Instrument`).

    The curated universe (`InstrumentUniverse` port) is config-driven, not a database
    table, so watchlist items reference instruments by their `symbol` string rather
    than a foreign key.
    """

    id: str
    watchlist_id: str
    symbol: str
    added_at: datetime = field(default_factory=lambda: datetime.now(UTC))
