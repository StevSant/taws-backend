import logging

from app.domain.market.entities import EarningsCalendarEntry, InstrumentFundamentals
from app.domain.market.errors import FundamentalsUnavailableError
from app.domain.market.ports import FundamentalsProvider

logger = logging.getLogger(__name__)


class RoutingFundamentalsProvider(FundamentalsProvider):
    """FundamentalsProvider fronting the live `yfinance` adapter. Real fundamentals, or an error.

    Used to degrade to `FixtureFundamentalsProvider` on any exception, so a yfinance hiccup
    silently became an invented P/E or earnings date — indistinguishable from a real one, and
    fed straight into the analyst's thesis.

    `get_earnings_calendar` still returns `None` when the provider legitimately has no
    upcoming earnings date for a symbol: that is a real answer ("nothing scheduled"), not a
    missing one, and the two must not be conflated.
    """

    def __init__(self, live_provider: FundamentalsProvider) -> None:
        self._live_provider = live_provider

    async def get_fundamentals(self, symbol: str) -> InstrumentFundamentals:
        try:
            return await self._live_provider.get_fundamentals(symbol)
        except Exception as error:
            logger.warning("Live fundamentals lookup failed for %s.", symbol, exc_info=True)
            raise FundamentalsUnavailableError(symbol, str(error)) from error

    async def get_earnings_calendar(self, symbol: str) -> EarningsCalendarEntry | None:
        try:
            return await self._live_provider.get_earnings_calendar(symbol)
        except Exception as error:
            logger.warning("Live earnings calendar lookup failed for %s.", symbol, exc_info=True)
            raise FundamentalsUnavailableError(symbol, str(error)) from error
