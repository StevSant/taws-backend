from abc import ABC, abstractmethod

from app.domain.market.entities import Instrument, PriceSeries


class MarketDataProvider(ABC):
    """Port for fetching REAL price data for a single instrument.

    Adapters: `yfinance` (stocks/ETFs/commodities/FX), CoinGecko (crypto), and the
    `RoutingMarketDataProvider` that picks the right one by asset class.

    **Contract: return real prices or raise `MarketDataUnavailableError`.** An adapter
    must never satisfy a call with data it made up, interpolated, or carried over from
    another asset. Prices from this port are consumed as fact by chart rendering, quant
    statistics, signal classification, and ultimately by investment advice shown to a
    user — so a fabricated number here does not stay a data-layer detail, it becomes a
    recommendation. There is no fixture adapter behind this port for exactly that reason;
    synthetic series live in `tests/` only.
    """

    @abstractmethod
    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        """Return the instrument's real daily OHLC series for the last `days` days.

        Raises `MarketDataUnavailableError` if real data can't be fetched.
        """
        raise NotImplementedError

    @abstractmethod
    async def get_last_price(self, instrument: Instrument) -> float | None:
        """Return the instrument's most recent real price.

        Raises `MarketDataUnavailableError` if real data can't be fetched. (`None` is
        still allowed by the type so the thin single-vendor adapters can express "I got
        nothing" to the router, which converts it into the error.)
        """
        raise NotImplementedError
