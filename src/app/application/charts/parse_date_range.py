from datetime import date


def parse_date_range(from_date: str | None, to_date: str | None) -> tuple[date, date] | None:
    """Parse an optional ISO `YYYY-MM-DD` range, returning `(from, to)` only when valid.

    Returns `None` when either bound is missing, unparseable, or out of order (`from > to`),
    signalling the caller to fall back to the timeframe/preset behavior. Never raises on bad
    input — an invalid custom range degrades to the preset, it does not error the request."""
    if not from_date or not to_date:
        return None
    try:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
    except ValueError:
        return None
    if start > end:
        return None
    return start, end
