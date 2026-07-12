from typing import Any

from app.domain.watchlist.entities import Watchlist
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def watchlist_from_row(row: Any) -> Watchlist:
    """Map one `watchlists` table row (as returned by `supabase-py`) onto `Watchlist`.

    Typed `Any` rather than `dict[str, Any]`: `postgrest`'s response rows are typed
    as the broad `JSON` union, which pyright won't narrow to `dict` automatically —
    this is an internal adapter helper, not part of the public port contract.
    """
    return Watchlist(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        created_at=parse_supabase_timestamp(row["created_at"]),
        position=row.get("position"),
    )
