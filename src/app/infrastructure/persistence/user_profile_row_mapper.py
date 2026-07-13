from typing import Any

from app.domain.profile.entities import UserProfile
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def user_profile_from_row(row: Any) -> UserProfile:
    """Map one `profiles` table row (as returned by `supabase-py`) onto `UserProfile`.

    Typed `Any` rather than `dict[str, Any]`: `postgrest`'s response rows are typed as the
    broad `JSON` union, which pyright won't narrow to `dict` automatically — same rationale
    as `note_row_mapper.py`.
    """
    return UserProfile(
        user_id=row["user_id"],
        preferred_locale=row["preferred_locale"],
        created_at=parse_supabase_timestamp(row["created_at"]),
        updated_at=parse_supabase_timestamp(row["updated_at"]),
    )
