from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EarningsCalendarEntry:
    """An instrument's next scheduled earnings date, with a simple "upcoming earnings risk" flag.

    `is_upcoming_risk` is a deliberately simple derived flag, not a risk model: `True` when
    `earnings_date` falls within `FundamentalsProvider`'s configured risk window (see
    `Settings.upcoming_earnings_risk_window_days`), `False` otherwise.
    """

    symbol: str
    earnings_date: datetime
    is_upcoming_risk: bool
