import asyncio
from datetime import UTC, date, datetime
from typing import Any

import yfinance as yf

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals
from app.domain.market.ports import FundamentalsProvider
from app.infrastructure.fundamentals.derive_upcoming_earnings_risk import (
    derive_upcoming_earnings_risk,
)


class YFinanceFundamentalsProvider(FundamentalsProvider):
    """FundamentalsProvider adapter backed by `yfinance`'s `Ticker.info` (basic fundamentals)
    and `Ticker.calendar` (earnings calendar).

    `yfinance` is synchronous, so every call is off-loaded to a worker thread via
    `asyncio.to_thread`, same as `YFinanceMarketDataProvider`. `Ticker.calendar`'s shape varies
    across `yfinance` versions (a `dict` in current releases, a `DataFrame` in older ones), so
    the next-earnings-date lookup handles both defensively rather than assuming one shape.
    """

    def __init__(self, risk_window_days: int) -> None:
        self._risk_window_days = risk_window_days

    async def get_fundamentals(self, symbol: str) -> InstrumentFundamentals:
        info = await asyncio.to_thread(self._fetch_info, symbol)
        return InstrumentFundamentals(
            symbol=symbol,
            market_cap=_as_float(info.get("marketCap")),
            pe_ratio=_as_float(info.get("trailingPE")),
            dividend_yield=_as_float(info.get("dividendYield")),
            sector=info.get("sector"),
        )

    async def get_earnings_calendar(self, symbol: str) -> EarningsCalendarEntry | None:
        earnings_date = await asyncio.to_thread(self._fetch_next_earnings_date, symbol)
        if earnings_date is None:
            return None
        now = datetime.now(UTC)
        is_upcoming_risk = derive_upcoming_earnings_risk(earnings_date, now, self._risk_window_days)
        return EarningsCalendarEntry(
            symbol=symbol, earnings_date=earnings_date, is_upcoming_risk=is_upcoming_risk
        )

    @staticmethod
    def _fetch_info(symbol: str) -> dict[str, Any]:
        ticker = yf.Ticker(symbol)
        return dict(ticker.info or {})

    @staticmethod
    def _fetch_next_earnings_date(symbol: str) -> datetime | None:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        raw_dates = _extract_earnings_dates(calendar)
        if not raw_dates:
            return None
        earliest = min(raw_dates)
        return datetime(earliest.year, earliest.month, earliest.day, tzinfo=UTC)


def _extract_earnings_dates(calendar: Any) -> list[date]:
    """Normalize `Ticker.calendar`'s "Earnings Date" entries into plain `date`s, across the
    dict-shaped (current `yfinance`) and DataFrame-shaped (older `yfinance`) return types.
    """
    if calendar is None:
        return []

    if isinstance(calendar, dict):
        raw = calendar.get("Earnings Date") or []
        raw_values = raw if isinstance(raw, list) else [raw]
    else:
        # Older yfinance: a DataFrame with an "Earnings Date" row.
        try:
            raw_values = list(calendar.loc["Earnings Date"])
        except (KeyError, AttributeError):
            return []

    dates: list[date] = []
    for value in raw_values:
        if isinstance(value, datetime):
            dates.append(value.date())
        elif isinstance(value, date):
            dates.append(value)
    return dates


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None
