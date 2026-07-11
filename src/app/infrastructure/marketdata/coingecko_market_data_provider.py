from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider


class CoinGeckoMarketDataProvider(MarketDataProvider):
    """MarketDataProvider adapter backed by the public CoinGecko API (no key needed).

    `coingecko_id_overrides` maps a domain symbol to its CoinGecko coin id (e.g.
    `BTC` -> `bitcoin`); symbols without an override fall back to their
    lowercased symbol, which will simply fail (and be caught upstream by
    `RoutingMarketDataProvider`) if that's not a valid CoinGecko id.
    """

    def __init__(
        self,
        base_url: str,
        coingecko_id_overrides: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url
        self._overrides = coingecko_id_overrides or {}
        self._timeout_seconds = timeout_seconds

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        coin_id = self._resolve_id(instrument)
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.get(
                f"/coins/{coin_id}/ohlc", params={"vs_currency": "usd", "days": days}
            )
            response.raise_for_status()
            payload = response.json()

        candles = [self._to_candle(point) for point in payload]
        return PriceSeries(symbol=instrument.symbol, candles=candles)

    async def get_last_price(self, instrument: Instrument) -> float | None:
        coin_id = self._resolve_id(instrument)
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.get(
                "/simple/price", params={"ids": coin_id, "vs_currencies": "usd"}
            )
            response.raise_for_status()
            payload = response.json()

        price = payload.get(coin_id, {}).get("usd")
        return float(price) if price is not None else None

    def _resolve_id(self, instrument: Instrument) -> str:
        return self._overrides.get(instrument.symbol, instrument.symbol.lower())

    @staticmethod
    def _to_candle(point: list[Any]) -> PriceCandle:
        timestamp_ms, open_price, high, low, close = point
        return PriceCandle(
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
            open=float(open_price),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=None,
        )
