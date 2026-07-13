import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.core.config import get_settings
from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider
from app.infrastructure.caching import TtlCache


class YFinanceMarketDataProvider(MarketDataProvider):
    """MarketDataProvider adapter backed by `yfinance`.

    Covers STOCK, CREDIT (bond ETFs), COMMODITY, and FOREX instruments in the
    curated universe. `yfinance` is synchronous, so every call is off-loaded to
    a worker thread via `asyncio.to_thread`. `symbol_overrides` maps a domain
    symbol to its yfinance ticker (e.g. `EURUSD` -> `EURUSD=X`); symbols without
    an override are queried as-is.

    `yfinance` uses `NaN` for missing OHLC values — an as-yet-unclosed trading day,
    a gap in an illiquid ETF's history, a holiday row. A `NaN` price is *missing*
    data, not real data, so rows with a non-finite open/high/low/close are dropped
    here rather than passed downstream: the API serializes responses with
    `allow_nan=False` (Starlette's `JSONResponse`), so a single `NaN` reaching the
    wire raised `ValueError` -> 500 on every equity/ETF `quant/stats` call while
    crypto (CoinGecko, no `NaN`) worked. Dropping the row keeps the "real prices or
    `MarketDataUnavailableError`" contract intact — if every row is dropped the
    series is empty, which `RoutingMarketDataProvider` maps to a clean 503.

    Short-TTL in-process cache (mirrors `CoinGeckoMarketDataProvider`, issue #8): the radar
    polls the same handful of instruments from every open browser every ~60s, and each read
    was a live Yahoo round-trip. Price series are cached by `(ticker, days)` and last prices
    by ticker; only genuinely-fetched data is cached (an empty series or `None` last price —
    a delisted ticker, a transient Yahoo hiccup, an all-`NaN` window — is never cached, so a
    momentary blank can't be pinned as unavailable for the whole TTL window). `cache_ttl_seconds`
    falls back to `Settings.yfinance_cache_ttl_seconds` when not injected.
    """

    def __init__(
        self,
        symbol_overrides: dict[str, str] | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        self._symbol_overrides = symbol_overrides or {}
        ttl = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else get_settings().yfinance_cache_ttl_seconds
        )
        self._price_series_cache: TtlCache[tuple[str, int], PriceSeries] = TtlCache(ttl)
        self._last_price_cache: TtlCache[str, float] = TtlCache(ttl)

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        ticker_symbol = self._resolve_symbol(instrument)
        cache_key = (ticker_symbol, days)
        cached = self._price_series_cache.get(cache_key)
        if cached is not None:
            return cached

        history = await asyncio.to_thread(self._fetch_history, ticker_symbol, days)
        candles = [
            candle
            for index, row in history.iterrows()
            if (candle := self._to_candle(index, row)) is not None
        ]
        series = PriceSeries(symbol=instrument.symbol, candles=candles)
        if candles:
            # An empty series is "no usable data right now", not a value worth pinning for the
            # whole TTL — `RoutingMarketDataProvider` maps it to a 503, so caching it would keep
            # the instrument dark until expiry even after Yahoo recovers.
            self._price_series_cache.set(cache_key, series)
        return series

    async def get_last_price(self, instrument: Instrument) -> float | None:
        ticker_symbol = self._resolve_symbol(instrument)
        cached = self._last_price_cache.get(ticker_symbol)
        if cached is not None:
            return cached

        history = await asyncio.to_thread(self._fetch_history, ticker_symbol, 1)
        if history.empty:
            return None
        close = float(history["Close"].iloc[-1])
        if not math.isfinite(close):
            return None
        self._last_price_cache.set(ticker_symbol, close)
        return close

    def _resolve_symbol(self, instrument: Instrument) -> str:
        return self._symbol_overrides.get(instrument.symbol, instrument.symbol)

    @staticmethod
    def _fetch_history(ticker_symbol: str, days: int) -> Any:
        ticker = yf.Ticker(ticker_symbol)
        return ticker.history(period=f"{max(days, 1)}d")

    @staticmethod
    def _to_candle(index: Any, row: Any) -> PriceCandle | None:
        open_, high, low, close = row["Open"], row["High"], row["Low"], row["Close"]
        if not all(_is_finite(value) for value in (open_, high, low, close)):
            # A NaN OHLC row is missing data, not a real bar — drop it (see class docstring).
            return None
        timestamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else datetime.now(UTC)
        volume = row.get("Volume")
        return PriceCandle(
            timestamp=timestamp,
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume) if _is_finite(volume) else None,
        )


def _is_finite(value: Any) -> bool:
    """True only for a real, finite number — rejects `None`, `NaN`, and `+/-inf`."""
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
