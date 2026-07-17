import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.domain.market.entities import MacroIndicator, MacroObservation, MacroSeries

_NO_DATA_ERROR = "[YFinanceGoldSeriesSource] No gold data returned by yfinance for {symbol!r}."


class YFinanceGoldSeriesSource:
    """Gold "Contexto de mercado" history sourced from yfinance (`GC=F`), not FRED.

    FRED's free daily gold fixing (`GOLDPMGBD228NLBM`, the LBMA London PM fixing) was
    discontinued, so `GET /api/v1/macro/series/gold` 503'd while the other four FRED-backed
    indicators kept working. This mirrors how the volatility regime already bypasses FRED for
    `^VIX`: gold now comes from yfinance daily closes over the requested window. `yfinance` is
    synchronous, so the fetch is off-loaded to a worker thread (same pattern as
    `YFinanceMarketDataProvider`).

    `yfinance` uses `NaN` for missing closes (an as-yet-unclosed session, a holiday row). A
    `NaN` price is *missing* data, not real data, so those rows are dropped rather than emitted.
    If every row is dropped the series is empty and this raises — surfacing upstream as
    `MacroDataUnavailableError` (a clean 503) rather than a fabricated gold price. yfinance
    history is already ordered oldest -> newest, which matches the `MacroSeries` contract.

    Unlike `get_rates`/`get_cpi`, this history read is deliberately uncached — same as
    `FredMacroDataProvider.get_indicator_history`: it takes a caller-supplied `days` window and
    backs the low-frequency sparkline, not the hot per-request path.
    """

    def __init__(self, symbol: str) -> None:
        self._symbol = symbol

    async def get_series(self, days: int) -> MacroSeries:
        history = await asyncio.to_thread(self._fetch_history, self._symbol, days)
        observations = [
            observation
            for index, row in history.iterrows()
            if (observation := self._to_observation(index, row)) is not None
        ]
        if not observations:
            raise RuntimeError(_NO_DATA_ERROR.format(symbol=self._symbol))
        return MacroSeries(
            indicator=MacroIndicator.GOLD,
            series_id=self._symbol,
            observations=observations,
        )

    @staticmethod
    def _fetch_history(symbol: str, days: int) -> Any:
        ticker = yf.Ticker(symbol)
        return ticker.history(period=f"{max(days, 1)}d")

    def _to_observation(self, index: Any, row: Any) -> MacroObservation | None:
        close = row.get("Close")
        if close is None or not math.isfinite(float(close)):
            # A NaN close is missing data, not a real print — drop it (see class docstring).
            return None
        as_of = index.to_pydatetime() if hasattr(index, "to_pydatetime") else datetime.now(UTC)
        return MacroObservation(series_id=self._symbol, value=float(close), as_of=as_of)
