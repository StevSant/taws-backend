import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import yfinance as yf

from app.domain.market.entities import MacroObservation, VolatilityRegime
from app.domain.market.ports import MacroDataProvider
from app.infrastructure.macro.bucket_volatility_regime import bucket_volatility_regime

_NO_KEY_ERROR = "[FredMacroDataProvider] No FRED_API_KEY configured."


class FredMacroDataProvider(MacroDataProvider):
    """MacroDataProvider adapter backed by the FRED API (rates, CPI) and `yfinance`'s `^VIX`
    ticker (volatility regime).

    `get_rates`/`get_cpi` require `FRED_API_KEY` — without one, both raise immediately instead
    of calling FRED (same no-key guard shape as `OpenAIProvider`). `get_volatility_regime` needs
    no key: it fetches `^VIX` the same way `YFinanceMarketDataProvider` fetches regular
    instruments (`yfinance`, off-loaded to a worker thread). Callers should wrap this adapter in
    `RoutingMacroDataProvider` rather than using it directly, so any failure — including the
    "no key" case — falls back to `FixtureMacroDataProvider` per method.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        rates_series_id: str,
        cpi_series_id: str,
        vix_symbol: str,
        low_threshold: float,
        elevated_threshold: float,
        high_threshold: float,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._rates_series_id = rates_series_id
        self._cpi_series_id = cpi_series_id
        self._vix_symbol = vix_symbol
        self._low_threshold = low_threshold
        self._elevated_threshold = elevated_threshold
        self._high_threshold = high_threshold
        self._timeout_seconds = timeout_seconds

    async def get_rates(self) -> MacroObservation:
        return await self._fetch_latest_observation(self._rates_series_id)

    async def get_cpi(self) -> MacroObservation:
        return await self._fetch_latest_observation(self._cpi_series_id)

    async def get_volatility_regime(self) -> VolatilityRegime:
        vix_level = await asyncio.to_thread(self._fetch_vix_level)
        regime = bucket_volatility_regime(
            vix_level, self._low_threshold, self._elevated_threshold, self._high_threshold
        )
        return VolatilityRegime(vix_level=vix_level, regime=regime, as_of=datetime.now(UTC))

    async def _fetch_latest_observation(self, series_id: str) -> MacroObservation:
        if not self._api_key:
            raise RuntimeError(_NO_KEY_ERROR)

        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.get(
                "/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
            )
            response.raise_for_status()
            payload = response.json()

        return _to_observation(series_id, payload)

    def _fetch_vix_level(self) -> float:
        ticker = yf.Ticker(self._vix_symbol)
        history = ticker.history(period="5d")
        if history.empty:
            raise RuntimeError("[FredMacroDataProvider] No VIX data returned by yfinance.")
        return float(history["Close"].iloc[-1])


def _to_observation(series_id: str, payload: dict[str, Any]) -> MacroObservation:
    observations = payload.get("observations") or []
    if not observations:
        raise RuntimeError(
            f"[FredMacroDataProvider] No observations returned by FRED for {series_id!r}."
        )
    latest = observations[0]
    return MacroObservation(
        series_id=series_id,
        value=float(latest["value"]),
        as_of=datetime.strptime(latest["date"], "%Y-%m-%d").replace(tzinfo=UTC),
    )
