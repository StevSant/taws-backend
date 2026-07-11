import logging

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals
from app.domain.market.ports import FundamentalsProvider

logger = logging.getLogger(__name__)


class RoutingFundamentalsProvider(FundamentalsProvider):
    """FundamentalsProvider that prefers the live `yfinance` adapter and falls back to fixtures.

    Any exception from the live adapter falls back to the deterministic
    `FixtureFundamentalsProvider`, per method — same shape as `RoutingMarketDataProvider` /
    `RoutingMacroDataProvider`, so a live-data outage never crashes the fundamentals/earnings
    lookup, it just degrades to fixture data.
    """

    def __init__(
        self, live_provider: FundamentalsProvider, fixture_provider: FundamentalsProvider
    ) -> None:
        self._live_provider = live_provider
        self._fixture_provider = fixture_provider

    async def get_fundamentals(self, symbol: str) -> InstrumentFundamentals:
        try:
            return await self._live_provider.get_fundamentals(symbol)
        except Exception:
            logger.warning(
                "Live fundamentals lookup failed for %s; using fixture.", symbol, exc_info=True
            )
            return await self._fixture_provider.get_fundamentals(symbol)

    async def get_earnings_calendar(self, symbol: str) -> EarningsCalendarEntry | None:
        try:
            return await self._live_provider.get_earnings_calendar(symbol)
        except Exception:
            logger.warning(
                "Live earnings calendar lookup failed for %s; using fixture.", symbol, exc_info=True
            )
            return await self._fixture_provider.get_earnings_calendar(symbol)
