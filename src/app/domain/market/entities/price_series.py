from dataclasses import dataclass

from app.domain.market.entities.price_candle import PriceCandle


@dataclass(frozen=True, slots=True)
class PriceSeries:
    """An ordered series of price candles for a single instrument symbol."""

    symbol: str
    candles: list[PriceCandle]
