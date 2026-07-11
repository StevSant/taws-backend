import hashlib
import random
from datetime import UTC, datetime, timedelta

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals
from app.domain.market.ports import FundamentalsProvider
from app.infrastructure.fundamentals.derive_upcoming_earnings_risk import (
    derive_upcoming_earnings_risk,
)

_SECTORS = ("Technology", "Financials", "Energy", "Healthcare", "Industrials")
_MIN_MARKET_CAP = 1_000_000_000.0
_MAX_MARKET_CAP = 2_000_000_000_000.0
_MIN_PE_RATIO = 8.0
_MAX_PE_RATIO = 45.0
_MAX_DIVIDEND_YIELD = 0.04
_MAX_EARNINGS_DAYS_AHEAD = 45


class FixtureFundamentalsProvider(FundamentalsProvider):
    """FundamentalsProvider fallback: deterministic synthetic fundamentals + earnings date per
    symbol, seeded from the symbol so repeated calls are stable.

    Used by `RoutingFundamentalsProvider` whenever a live `yfinance` call fails, keeping
    "upcoming earnings risk" tagging available without any live data dependency — consistent
    with `FixtureMarketDataProvider`.
    """

    def __init__(self, risk_window_days: int) -> None:
        self._risk_window_days = risk_window_days

    async def get_fundamentals(self, symbol: str) -> InstrumentFundamentals:
        rng = _rng_for(symbol)
        return InstrumentFundamentals(
            symbol=symbol,
            market_cap=round(
                _MIN_MARKET_CAP + rng.random() * (_MAX_MARKET_CAP - _MIN_MARKET_CAP), 2
            ),
            pe_ratio=round(_MIN_PE_RATIO + rng.random() * (_MAX_PE_RATIO - _MIN_PE_RATIO), 2),
            dividend_yield=round(rng.random() * _MAX_DIVIDEND_YIELD, 4),
            sector=_SECTORS[rng.randrange(len(_SECTORS))],
        )

    async def get_earnings_calendar(self, symbol: str) -> EarningsCalendarEntry | None:
        rng = _rng_for(symbol)
        days_ahead = rng.randrange(0, _MAX_EARNINGS_DAYS_AHEAD)
        now = datetime.now(UTC)
        earnings_date = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=days_ahead
        )
        is_upcoming_risk = derive_upcoming_earnings_risk(earnings_date, now, self._risk_window_days)
        return EarningsCalendarEntry(
            symbol=symbol, earnings_date=earnings_date, is_upcoming_risk=is_upcoming_risk
        )


def _rng_for(symbol: str) -> random.Random:
    seed = int(hashlib.sha256(symbol.upper().encode()).hexdigest(), 16) % (2**32)
    return random.Random(seed)
