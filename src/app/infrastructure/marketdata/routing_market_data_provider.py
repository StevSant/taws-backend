import logging

from app.domain.market.entities import AssetClass, Instrument, PriceSeries
from app.domain.market.errors import MarketDataUnavailableError
from app.domain.market.ports import MarketDataProvider

logger = logging.getLogger(__name__)


class RoutingMarketDataProvider(MarketDataProvider):
    """MarketDataProvider that routes by asset class: CRYPTO -> CoinGecko, else yfinance.

    Real data or `MarketDataUnavailableError` — there is no third outcome. This provider
    used to fall back to a `FixtureMarketDataProvider` (a symbol-seeded random walk in a
    $20-$500 band) on any exception OR empty result, so a routine CoinGecko 429 silently
    became invented prices that were indistinguishable from real ones at every layer above
    here: BTC was charted to a user at $333.6 while it traded near $63,000, and the agent
    reasoned an investment recommendation on top of the fabrication.

    An empty result is a failure, not "this asset has no history": every instrument in the
    universe is one an upstream provider is expected to price, so zero candles means the
    lookup did not work — which is exactly what CoinGecko's circuit breaker returns while
    it is backing off.
    """

    def __init__(
        self,
        yfinance_provider: MarketDataProvider,
        coingecko_provider: MarketDataProvider,
    ) -> None:
        self._yfinance_provider = yfinance_provider
        self._coingecko_provider = coingecko_provider

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        try:
            series = await self._primary_for(instrument).get_price_series(instrument, days)
        except MarketDataUnavailableError:
            raise
        except Exception as error:
            logger.warning(
                "Live price series lookup failed for %s.", instrument.symbol, exc_info=True
            )
            raise MarketDataUnavailableError(instrument.symbol, str(error)) from error

        if not series.candles:
            logger.warning("Live price series for %s came back empty.", instrument.symbol)
            raise MarketDataUnavailableError(
                instrument.symbol, "upstream provider returned no candles"
            )
        return series

    async def get_last_price(self, instrument: Instrument) -> float:
        try:
            price = await self._primary_for(instrument).get_last_price(instrument)
        except MarketDataUnavailableError:
            raise
        except Exception as error:
            logger.warning(
                "Live last-price lookup failed for %s.", instrument.symbol, exc_info=True
            )
            raise MarketDataUnavailableError(instrument.symbol, str(error)) from error

        if price is None:
            logger.warning("Live last price for %s came back empty.", instrument.symbol)
            raise MarketDataUnavailableError(
                instrument.symbol, "upstream provider returned no price"
            )
        return price

    def _primary_for(self, instrument: Instrument) -> MarketDataProvider:
        if instrument.asset_class == AssetClass.CRYPTO:
            return self._coingecko_provider
        return self._yfinance_provider
