from abc import ABC, abstractmethod

from app.domain.market.entities import Instrument, PriceSeries


class MarketDataProvider(ABC):
    """Port for fetching price data for a single instrument.

    Adapters: `yfinance` (stocks/ETFs/commodities/FX), CoinGecko (crypto), a
    deterministic fixture fallback, and a `RoutingMarketDataProvider` that picks
    the right live adapter by asset class and falls back to the fixture on any
    failure or empty result.
    """

    @abstractmethod
    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        """Return the instrument's daily OHLC price series for the last `days` days."""
        raise NotImplementedError

    @abstractmethod
    async def get_last_price(self, instrument: Instrument) -> float | None:
        """Return the instrument's most recent price, or `None` if unavailable."""
        raise NotImplementedError
