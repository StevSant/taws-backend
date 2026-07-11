from datetime import datetime


def derive_upcoming_earnings_risk(
    earnings_date: datetime, now: datetime, risk_window_days: int
) -> bool:
    """Return `True` when `earnings_date` falls within `risk_window_days` of `now` (inclusive,
    and never for a date already in the past).

    Deliberately simple derived flag, not a risk model — see `FundamentalsProvider`'s docstring.
    Shared by `YFinanceFundamentalsProvider` (live) and `FixtureFundamentalsProvider` (fixture)
    so the "upcoming earnings risk" rule never drifts between the two.
    """
    days_until = (earnings_date.date() - now.date()).days
    return 0 <= days_until <= risk_window_days
