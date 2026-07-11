import hashlib
import random
from datetime import UTC, datetime, timedelta

from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider

_BASE_PRICE_FLOOR = 20.0
_BASE_PRICE_RANGE = 480.0
_DAILY_VOLATILITY = 0.02
_MIN_VOLUME = 1_000_000.0
_MAX_VOLUME = 50_000_000.0


class FixtureMarketDataProvider(MarketDataProvider):
    """MarketDataProvider fallback: a deterministic synthetic random walk per symbol.

    Seeded from the instrument symbol, so repeated calls for the same symbol
    return an identical series ("stable between calls"). Used by
    `RoutingMarketDataProvider` whenever a live adapter errors or returns no data.
    """

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        candles = self._build_series(instrument.symbol, max(days, 1))
        return PriceSeries(symbol=instrument.symbol, candles=candles)

    async def get_last_price(self, instrument: Instrument) -> float | None:
        candles = self._build_series(instrument.symbol, 1)
        return candles[-1].close if candles else None

    @staticmethod
    def _build_series(symbol: str, days: int) -> list[PriceCandle]:
        seed = int(hashlib.sha256(symbol.upper().encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        price = _BASE_PRICE_FLOOR + rng.random() * _BASE_PRICE_RANGE
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        candles: list[PriceCandle] = []
        for offset in range(days, 0, -1):
            open_price = price
            change = rng.uniform(-_DAILY_VOLATILITY, _DAILY_VOLATILITY)
            close_price = max(open_price * (1 + change), 0.01)
            high_price = max(open_price, close_price) * (1 + rng.uniform(0, _DAILY_VOLATILITY / 2))
            low_price = min(open_price, close_price) * (1 - rng.uniform(0, _DAILY_VOLATILITY / 2))
            volume = rng.uniform(_MIN_VOLUME, _MAX_VOLUME)
            candles.append(
                PriceCandle(
                    timestamp=today - timedelta(days=offset - 1),
                    open=round(open_price, 4),
                    high=round(high_price, 4),
                    low=round(low_price, 4),
                    close=round(close_price, 4),
                    volume=round(volume, 2),
                )
            )
            price = close_price
        return candles
