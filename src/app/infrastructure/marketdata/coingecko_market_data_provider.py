import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider
from app.infrastructure.caching import TtlCache
from app.infrastructure.marketdata.coingecko_get import coingecko_get
from app.infrastructure.marketdata.coingecko_key_ring import CoinGeckoKeyRing
from app.infrastructure.marketdata.coingecko_rate_limited_error import CoinGeckoRateLimitedError

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
        key_ring: CoinGeckoKeyRing | None = None,
        cooldown_seconds: float = 300.0,
        max_history_days: int = 365,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._overrides = coingecko_id_overrides or {}
        self._timeout_seconds = timeout_seconds
        # Shared pooled client threaded through `coingecko_get` (issue #71 perf); `None` keeps
        # the per-call client behavior used by the failover unit tests. See `coingecko_get`.
        self._http_client = http_client
        # Public/Demo tiers refuse windows beyond this with `error_code: 10012`. Clamp instead
        # of sending a request we know will 400 — the `max` chart timeframe asks for 1825 days.
        self._max_history_days = max_history_days
        # The Demo API keys, tried in order with failover on a 429 (see `CoinGeckoKeyRing`).
        # Shared with the metadata/search adapters — one key's quota is spent by all three.
        # Defaults to an empty ring, i.e. the keyless public API.
        self._key_ring = key_ring or CoinGeckoKeyRing([])
        # Short-TTL cache (issue #8): CoinGecko's free tier rate-limits (429) hard when
        # the same handful of crypto instruments get polled every ~60s. Keyed by
        # `(coin_id, days)` for series, plain `coin_id` for last-price — two independent
        # caches since they hit different endpoints and shapes.
        self._price_series_cache: TtlCache[tuple[str, int], PriceSeries] = TtlCache(
            cache_ttl_seconds
        )
        self._last_price_cache: TtlCache[str, float | None] = TtlCache(cache_ttl_seconds)
        # Circuit breaker for when CoinGecko itself is DOWN (5xx / unreachable): the TtlCache
        # only ever stores *successful* responses, so while CoinGecko is failing the cache
        # never populates and every request re-hits the live API — turning one outage into a
        # continuous per-poll storm. Back off for `cooldown_seconds` and report prices as
        # unavailable instead. `None` = not currently backing off.
        #
        # Rate limits (429) are deliberately NOT this breaker's job anymore: they are handled
        # per-key by `CoinGeckoKeyRing`, which benches only the throttled key and fails the
        # same request over to the next one. Tripping this provider-wide breaker on a 429 was
        # exactly what turned one exhausted key into a 5-minute blackout of EVERY crypto
        # instrument (the `503 No real market data available for BTC` the radar surfaced).
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float | None = None

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        coin_id = self._resolve_id(instrument)
        window_days = min(days, self._max_history_days)
        cache_key = (coin_id, window_days)
        cached = self._price_series_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._in_cooldown():
            return PriceSeries(symbol=instrument.symbol, candles=[])

        try:
            payload = await coingecko_get(
                base_url=self._base_url,
                path=f"/coins/{coin_id}/market_chart",
                params={"vs_currency": "usd", "days": window_days, "interval": "daily"},
                timeout_seconds=self._timeout_seconds,
                key_ring=self._key_ring,
                http_client=self._http_client,
            )
        except CoinGeckoRateLimitedError:
            # Every key is throttled. The ring is already timing each key's comeback, so do
            # NOT also trip the provider-wide breaker — that would keep crypto dark for the
            # full `cooldown_seconds` even after a key's per-minute window rolled over.
            return PriceSeries(symbol=instrument.symbol, candles=[])
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
            payload = await coingecko_get(
                base_url=self._base_url,
                path="/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
                timeout_seconds=self._timeout_seconds,
                key_ring=self._key_ring,
                http_client=self._http_client,
            )
        except CoinGeckoRateLimitedError:
            return None
        except httpx.HTTPError as error:
            self._enter_cooldown(error)
            return None

        price = payload.get(coin_id, {}).get("usd")
        result = float(price) if price is not None else None
        self._last_price_cache.set(coin_id, result)
        return result

    def _resolve_id(self, instrument: Instrument) -> str:
        return self._overrides.get(instrument.symbol, instrument.symbol.lower())

    def _in_cooldown(self) -> bool:
        """True while backing off from a recent live failure; clears itself once elapsed."""
        if self._cooldown_until is None:
            return False
        if time.monotonic() >= self._cooldown_until:
            self._cooldown_until = None
            return False
        return True

    def _enter_cooldown(self, error: Exception) -> None:
        """Back off from CoinGecko, but ONLY when backing off is the right answer.

        A 5xx (API down) or a network failure means "stop calling me" — backing off is
        correct. A 4xx means WE sent a bad request; the API is perfectly healthy, and
        silencing it for the whole cooldown window punishes every other instrument for one
        malformed call. That distinction is not academic: the `max` chart timeframe asked
        for 1825 days, CoinGecko's public tier caps history at 365 and rejected it with a
        400, and that single 400 blanked out crypto pricing for 5 minutes — which is how a
        user clicking "max" ended up looking at a synthetic BTC chart.

        A 429 no longer reaches here at all: `coingecko_get` turns it into a
        `CoinGeckoRateLimitedError` after exhausting the key ring, and the caller returns empty
        without arming this breaker. `_is_client_error` still excludes 429 as defense in
        depth, in case a future call site bypasses `coingecko_get`.
        """
        if _is_client_error(error):
            logger.warning("CoinGecko rejected our request (%s); not backing off.", error)
            return
        self._cooldown_until = time.monotonic() + self._cooldown_seconds
        logger.warning(
            "CoinGecko unavailable (%s); backing off for %.0fs. Crypto prices will be "
            "reported as unavailable until it recovers.",
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


def _is_client_error(error: Exception) -> bool:
    """True for a 4xx OTHER than 429 — i.e. our request was wrong, not CoinGecko's fault.

    429 is excluded deliberately: it is nominally 4xx but it genuinely means "stop calling
    me", and that is the key ring's job (bench the throttled key, fail over to the next),
    not this provider-wide breaker's.
    """
    if not isinstance(error, httpx.HTTPStatusError):
        return False
    status = error.response.status_code
    return 400 <= status < 500 and status != 429
