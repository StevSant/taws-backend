import logging

from app.domain.market.entities import AssetClass, Instrument, PriceSeries
from app.domain.market.ports import MarketDataProvider

logger = logging.getLogger(__name__)


class RoutingMarketDataProvider(MarketDataProvider):
    """MarketDataProvider that routes by asset class and falls back to fixtures.

    CRYPTO instruments go to CoinGecko; everything else (STOCK, CREDIT,
    COMMODITY, FOREX) goes to `yfinance`. Any exception, or an empty/missing
    result, falls back to the deterministic `FixtureMarketDataProvider` so
    callers never see a live-data outage as a crash.
    """

    def __init__(
        self,
        yfinance_provider: MarketDataProvider,
        coingecko_provider: MarketDataProvider,
        fixture_provider: MarketDataProvider,
    ) -> None:
        self._yfinance_provider = yfinance_provider
        self._coingecko_provider = coingecko_provider
        self._fixture_provider = fixture_provider

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        try:
            series = await self._primary_for(instrument).get_price_series(instrument, days)
            if series.candles:
                return series
        except Exception:
            logger.warning(
                "Live price series lookup failed for %s; using fixture.",
                instrument.symbol,
                exc_info=True,
            )
        return await self._fixture_provider.get_price_series(instrument, days)

    async def get_last_price(self, instrument: Instrument) -> float | None:
        try:
            price = await self._primary_for(instrument).get_last_price(instrument)
            if price is not None:
                return price
        except Exception:
            logger.warning(
                "Live last-price lookup failed for %s; using fixture.",
                instrument.symbol,
                exc_info=True,
            )
        return await self._fixture_provider.get_last_price(instrument)

    def _primary_for(self, instrument: Instrument) -> MarketDataProvider:
        if instrument.asset_class == AssetClass.CRYPTO:
            return self._coingecko_provider
        return self._yfinance_provider
