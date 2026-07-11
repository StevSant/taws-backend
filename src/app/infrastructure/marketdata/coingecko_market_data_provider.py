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

    `get_price_series` calls `/coins/{id}/market_chart` with `interval=daily`
    rather than `/coins/{id}/ohlc`. CoinGecko's `/ohlc` endpoint silently
    auto-adjusts bar width based on the `days` parameter (30-minute bars for
    `days<=2`, 4-hour bars for `days` 3-30, 4-day bars for `days>=31`) instead
    of returning one candle per calendar day like `YFinanceMarketDataProvider`
    does for stocks/FX/commodities. The whole `application/quant/` stack
    (annualized-volatility `sqrt(252)`, the unusual-move z-score, and
    `ComputeEventStudy`'s `move_threshold_pct`) assumes one candle == one
    trading day; feeding it 4-hour or 4-day crypto bars silently corrupts
    every one of those statistics (confirmed live: BTC annualized volatility
    swung between "low" and "high" for the same underlying period purely
    from `/ohlc`'s candle-width auto-adjustment across different
    `window_days` values). `market_chart?interval=daily` was verified live
    against the real API to return genuinely daily-spaced points (~24h apart,
    with only the final in-progress "today" point closer than 24h) across the
    2-365 day range this port is called with, so this keeps the "one candle
    per day" contract true for every adapter without touching the shared
    quant math. `market_chart` doesn't provide intraday open/high/low (only a
    single sampled price per day), so `open`/`high`/`low`/`close` all collapse
    to that price — acceptable because nothing in `application/quant/` reads
    anything but `.close`/`.timestamp` off a `PriceCandle`.
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
                f"/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": days, "interval": "daily"},
            )
            response.raise_for_status()
            payload = response.json()

        candles = [self._to_candle(point) for point in payload.get("prices", [])]
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
        """Build a `PriceCandle` from one `market_chart` `prices` entry: `[timestamp_ms, price]`.

        `market_chart` (unlike `/ohlc`) has no intraday open/high/low, so all four OHLC
        fields collapse to the single sampled daily price — see the class docstring for
        why that's fine here (nothing downstream reads anything but `.close`/`.timestamp`).
        """
        timestamp_ms, price = point
        price = float(price)
        return PriceCandle(
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=None,
        )
