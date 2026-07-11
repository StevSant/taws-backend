import asyncio
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.domain.market.entities import Instrument, PriceCandle, PriceSeries
from app.domain.market.ports import MarketDataProvider


class YFinanceMarketDataProvider(MarketDataProvider):
    """MarketDataProvider adapter backed by `yfinance`.

    Covers STOCK, CREDIT (bond ETFs), COMMODITY, and FOREX instruments in the
    curated universe. `yfinance` is synchronous, so every call is off-loaded to
    a worker thread via `asyncio.to_thread`. `symbol_overrides` maps a domain
    symbol to its yfinance ticker (e.g. `EURUSD` -> `EURUSD=X`); symbols without
    an override are queried as-is.
    """

    def __init__(self, symbol_overrides: dict[str, str] | None = None) -> None:
        self._symbol_overrides = symbol_overrides or {}

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        ticker_symbol = self._resolve_symbol(instrument)
        history = await asyncio.to_thread(self._fetch_history, ticker_symbol, days)
        candles = [self._to_candle(index, row) for index, row in history.iterrows()]
        return PriceSeries(symbol=instrument.symbol, candles=candles)

    async def get_last_price(self, instrument: Instrument) -> float | None:
        ticker_symbol = self._resolve_symbol(instrument)
        history = await asyncio.to_thread(self._fetch_history, ticker_symbol, 1)
        if history.empty:
            return None
        return float(history["Close"].iloc[-1])

    def _resolve_symbol(self, instrument: Instrument) -> str:
        return self._symbol_overrides.get(instrument.symbol, instrument.symbol)

    @staticmethod
    def _fetch_history(ticker_symbol: str, days: int) -> Any:
        ticker = yf.Ticker(ticker_symbol)
        return ticker.history(period=f"{max(days, 1)}d")

    @staticmethod
    def _to_candle(index: Any, row: Any) -> PriceCandle:
        timestamp = index.to_pydatetime() if hasattr(index, "to_pydatetime") else datetime.now(UTC)
        volume = row.get("Volume")
        return PriceCandle(
            timestamp=timestamp,
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=float(volume) if volume is not None else None,
        )
