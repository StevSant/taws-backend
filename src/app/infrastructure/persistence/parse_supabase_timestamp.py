from datetime import datetime


def parse_supabase_timestamp(value: str) -> datetime:
    """Parse a Postgres/PostgREST timestamptz string into an aware `datetime`.

    Shared by every `*_row_mapper` module — PostgREST returns ISO-8601, occasionally
    with a trailing `Z` instead of an explicit `+00:00` offset, which
    `datetime.fromisoformat` only accepts on Python 3.11+ after normalizing it.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
