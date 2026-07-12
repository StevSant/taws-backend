import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider
from app.infrastructure.caching import TtlCache

logger = logging.getLogger(__name__)


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
        cache_ttl_seconds: float = 60.0,
        api_key: str | None = None,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url
        self._overrides = coingecko_id_overrides or {}
        self._timeout_seconds = timeout_seconds
        # Optional free "Demo" API key, sent as the `x-cg-demo-api-key` header to lift the
        # keyless public rate limits. Empty string -> None -> no header (keyless mode).
        self._api_key = api_key or None
        # Short-TTL cache (issue #8): CoinGecko's free tier rate-limits (429) hard when
        # the same handful of crypto instruments get polled every ~60s. Keyed by
        # `(coin_id, days)` for series, plain `coin_id` for last-price — two independent
        # caches since they hit different endpoints and shapes.
        self._price_series_cache: TtlCache[tuple[str, int], PriceSeries] = TtlCache(
            cache_ttl_seconds
        )
        self._last_price_cache: TtlCache[str, float | None] = TtlCache(cache_ttl_seconds)
        # Circuit breaker: the TtlCache only ever stores *successful* responses, so while
        # CoinGecko is rate-limiting (429) the cache never populates and every request
        # re-hits the live API — turning one 429 into a continuous per-poll storm. Once a
        # live call fails, back off for `cooldown_seconds` and serve fixtures (by returning
        # an empty result the RoutingMarketDataProvider falls back on) instead of hammering
        # the API on every poll. `None` = not currently backing off.
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float | None = None

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        coin_id = self._resolve_id(instrument)
        cache_key = (coin_id, days)
        cached = self._price_series_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._in_cooldown():
            return PriceSeries(symbol=instrument.symbol, candles=[])

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds, headers=self._headers()
            ) as client:
                response = await client.get(
                    f"/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": days, "interval": "daily"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as error:
            self._enter_cooldown(error)
            return PriceSeries(symbol=instrument.symbol, candles=[])

        candles = [self._to_candle(point) for point in payload.get("prices", [])]
        series = PriceSeries(symbol=instrument.symbol, candles=candles)
        self._price_series_cache.set(cache_key, series)
        return series

    async def get_last_price(self, instrument: Instrument) -> float | None:
        coin_id = self._resolve_id(instrument)
        cached = self._last_price_cache.get(coin_id)
        if cached is not None:
            return cached
        if self._in_cooldown():
            return None

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds, headers=self._headers()
            ) as client:
                response = await client.get(
                    "/simple/price", params={"ids": coin_id, "vs_currencies": "usd"}
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as error:
            self._enter_cooldown(error)
            return None

        price = payload.get(coin_id, {}).get("usd")
        result = float(price) if price is not None else None
        self._last_price_cache.set(coin_id, result)
        return result

    def _resolve_id(self, instrument: Instrument) -> str:
        return self._overrides.get(instrument.symbol, instrument.symbol.lower())

    def _headers(self) -> dict[str, str]:
        """CoinGecko Demo API key header when configured; empty (keyless) otherwise."""
        return {"x-cg-demo-api-key": self._api_key} if self._api_key else {}

    def _in_cooldown(self) -> bool:
        """True while backing off from a recent live failure; clears itself once elapsed."""
        if self._cooldown_until is None:
            return False
        if time.monotonic() >= self._cooldown_until:
            self._cooldown_until = None
            return False
        return True

    def _enter_cooldown(self, error: Exception) -> None:
        """Back off from CoinGecko after a live failure, logging once per cooldown window."""
        self._cooldown_until = time.monotonic() + self._cooldown_seconds
        logger.warning(
            "CoinGecko unavailable (%s); backing off for %.0fs and serving fixtures.",
            error,
            self._cooldown_seconds,
        )

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
