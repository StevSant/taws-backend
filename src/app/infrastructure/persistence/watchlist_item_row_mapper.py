from typing import Any

from app.domain.watchlist.entities import WatchlistItem
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def watchlist_item_from_row(row: Any) -> WatchlistItem:
    """Map one `watchlist_items` table row (as returned by `supabase-py`) onto `WatchlistItem`.

    Typed `Any` rather than `dict[str, Any]` — see `watchlist_row_mapper.py` for why.
    """
    return WatchlistItem(
        id=row["id"],
        watchlist_id=row["watchlist_id"],
        symbol=row["symbol"],
        added_at=parse_supabase_timestamp(row["added_at"]),
    )
