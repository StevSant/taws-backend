from typing import Any

from app.domain.briefing.entities import Briefing
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def briefing_from_row(row: Any) -> Briefing:
    """Map one `briefings` table row (as returned by `supabase-py`) onto `Briefing`.

    Typed `Any` rather than `dict[str, Any]` — see `watchlist_row_mapper.py` for why.
    """
    return Briefing(
        id=row["id"],
        watchlist_id=row["watchlist_id"],
        summary=row["summary"],
        disclaimer=row["disclaimer"],
        linked_signal_ids=row.get("linked_signal_ids") or [],
        created_at=parse_supabase_timestamp(row["created_at"]),
    )
