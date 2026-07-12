from typing import Any

from app.domain.notes.entities import Note
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def note_from_row(row: Any) -> Note:
    """Map one `user_notes` table row (as returned by `supabase-py`) onto `Note`.

    Typed `Any` rather than `dict[str, Any]`: `postgrest`'s response rows are typed as the
    broad `JSON` union, which pyright won't narrow to `dict` automatically — same rationale
    as `watchlist_row_mapper.py`.
    """
    return Note(
        id=row["id"],
        user_id=row["user_id"],
        body=row["body"],
        created_at=parse_supabase_timestamp(row["created_at"]),
        updated_at=parse_supabase_timestamp(row["updated_at"]),
    )
