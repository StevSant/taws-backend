from abc import ABC, abstractmethod

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals


class FundamentalsProvider(ABC):
    """Port for company fundamentals and the earnings calendar ("upcoming earnings risk").

    Kept separate from `MarketDataProvider`: real-time/historical OHLC price data and
    fundamentals/earnings-calendar data are distinct concerns with different vendor shapes and
    refresh cadence, and `MarketDataProvider`'s interface is already small and focused (see
    issue #15's design guidance). Adapter: `yfinance` (`Ticker.info` + `Ticker.calendar`), with
    a deterministic fixture fallback — see `infrastructure/fundamentals/`.
    """

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> InstrumentFundamentals:
        """Return basic fundamentals for `symbol` (fields are `None` where unavailable)."""
        raise NotImplementedError

    @abstractmethod
    async def get_earnings_calendar(self, symbol: str) -> EarningsCalendarEntry | None:
        """Return `symbol`'s next scheduled earnings date + risk flag, or `None` if no upcoming
        earnings date is available (e.g. non-equity instruments)."""
        raise NotImplementedError
