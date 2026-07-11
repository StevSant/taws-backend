from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UnusualMove:
    """A single trading day flagged as an unusual move within a `MarketStats` window.

    "Unusual" = the day's close-over-close return's z-score (against the window's own
    mean/stdev of daily returns) exceeds the threshold in `compute_market_stats.py` —
    see that module's docstring for why a z-score is used instead of a fixed percentage.
    """

    date: datetime
    return_pct: float
    z_score: float
