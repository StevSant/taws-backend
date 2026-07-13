import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import yfinance as yf

from app.core.config import get_settings
from app.domain.market.entities import (
    MacroIndicator,
    MacroObservation,
    MacroSeries,
    VolatilityRegime,
)
from app.domain.market.ports import MacroDataProvider
from app.infrastructure.caching import TtlCache
from app.infrastructure.macro.bucket_volatility_regime import bucket_volatility_regime

_NO_KEY_ERROR = "[FredMacroDataProvider] No FRED_API_KEY configured."


class FredMacroDataProvider(MacroDataProvider):
    """MacroDataProvider adapter backed by the FRED API (rates, CPI) and `yfinance`'s `^VIX`
    ticker (volatility regime).

    `get_rates`/`get_cpi` require `FRED_API_KEY` — without one, both raise immediately instead
    of calling FRED (same no-key guard shape as `OpenAIProvider`). `get_cpi` returns the
    year-over-year % change of the CPI index series (not the raw index level).
    `get_volatility_regime` needs no key: it fetches `^VIX` the same way
    `YFinanceMarketDataProvider` fetches regular instruments (`yfinance`, off-loaded to a
    worker thread). Callers should wrap this adapter in `RoutingMacroDataProvider` rather
    than using it directly, so any failure — including the "no key" case — surfaces as
    `MacroDataUnavailableError` per method instead of being answered with invented figures.

    Macro series move slowly (rates monthly, CPI monthly, VIX daily) but every macro-aware
    pipeline re-reads them per request, so each `get_rates`/`get_cpi`/`get_volatility_regime`
    was a live FRED/Yahoo round-trip. All three are cached in-process (mirrors
    `CoinGeckoMarketDataProvider`, issue #8), keyed by their series id / symbol; only successful
    reads are cached, so a transient upstream failure still surfaces as
    `MacroDataUnavailableError` rather than being pinned. `get_indicator_history` is left
    uncached on purpose: it takes a caller-supplied `days` window and backs the lower-frequency
    "Contexto de mercado" sparklines, not the hot per-request path. `cache_ttl_seconds` falls
    back to `Settings.fred_cache_ttl_seconds` when not injected.
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
        indicator_series_ids: dict[MacroIndicator, str],
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        # Optional shared pooled client (issue #71 perf): when injected, each FRED read reuses
        # its warm connection pool + TLS session instead of opening a fresh client per call, and
        # it is never closed here. `None` keeps the original per-call `httpx.AsyncClient` path.
        self._http_client = http_client
        self._rates_series_id = rates_series_id
        self._cpi_series_id = cpi_series_id
        self._vix_symbol = vix_symbol
        self._indicator_series_ids = indicator_series_ids
        self._low_threshold = low_threshold
        self._elevated_threshold = elevated_threshold
        self._high_threshold = high_threshold
        self._timeout_seconds = timeout_seconds
        ttl = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else get_settings().fred_cache_ttl_seconds
        )
        # Rates and CPI both yield a `MacroObservation`; keys are prefixed so the two series
        # can never collide even if an operator misconfigures them to the same series id.
        self._observation_cache: TtlCache[str, MacroObservation] = TtlCache(ttl)
        self._vix_cache: TtlCache[str, VolatilityRegime] = TtlCache(ttl)

    async def get_rates(self) -> MacroObservation:
        cache_key = f"rates:{self._rates_series_id}"
        cached = self._observation_cache.get(cache_key)
        if cached is not None:
            return cached
        observation = await self._fetch_latest_observation(self._rates_series_id)
        self._observation_cache.set(cache_key, observation)
        return observation

    async def get_cpi(self) -> MacroObservation:
        """Return headline CPI as year-over-year % change (not the raw index level)."""
        cache_key = f"cpi:{self._cpi_series_id}"
        cached = self._observation_cache.get(cache_key)
        if cached is not None:
            return cached
        observation = await self._fetch_cpi_yoy(self._cpi_series_id)
        self._observation_cache.set(cache_key, observation)
        return observation

    async def get_volatility_regime(self) -> VolatilityRegime:
        cached = self._vix_cache.get(self._vix_symbol)
        if cached is not None:
            return cached
        vix_level = await asyncio.to_thread(self._fetch_vix_level)
        regime = bucket_volatility_regime(
            vix_level, self._low_threshold, self._elevated_threshold, self._high_threshold
        )
        reading = VolatilityRegime(vix_level=vix_level, regime=regime, as_of=datetime.now(UTC))
        self._vix_cache.set(self._vix_symbol, reading)
        return reading

    async def get_indicator_history(self, indicator: MacroIndicator, days: int) -> MacroSeries:
        series_id = self._indicator_series_ids.get(indicator)
        if series_id is None:
            raise RuntimeError(
                f"[FredMacroDataProvider] No FRED series id configured for {indicator!r}."
            )
        if not self._api_key:
            raise RuntimeError(_NO_KEY_ERROR)

        payload = await self._request_observations(
            {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": days,
            }
        )

        parsed = _parse_fred_observations(payload)
        if not parsed:
            raise RuntimeError(
                f"[FredMacroDataProvider] No observations returned by FRED for {series_id!r}."
            )
        # FRED returns newest-first; the series contract is oldest-first.
        observations = [
            MacroObservation(series_id=series_id, value=value, as_of=as_of)
            for as_of, value in reversed(parsed)
        ]
        return MacroSeries(indicator=indicator, series_id=series_id, observations=observations)

    async def _request_observations(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET FRED's `/series/observations` with `params` and return the parsed JSON body.

        The three FRED reads (indicator history, latest observation, CPI YoY) differ only in
        `params`, so the transport lives here once. When the shared pooled client is injected
        (issue #71 perf) each read reuses its warm connection pool + TLS session — absolute URL
        and per-request timeout, never closing it — otherwise it keeps the original per-call
        `httpx.AsyncClient(base_url=..., timeout=...)` behavior.
        """
        if self._http_client is not None:
            response = await self._http_client.get(
                f"{self._base_url.rstrip('/')}/series/observations",
                params=params,
                timeout=self._timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.get("/series/observations", params=params)
        response.raise_for_status()
        return response.json()

    async def _fetch_latest_observation(self, series_id: str) -> MacroObservation:
        if not self._api_key:
            raise RuntimeError(_NO_KEY_ERROR)

        payload = await self._request_observations(
            {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            }
        )

        return _to_observation(series_id, payload)

    async def _fetch_cpi_yoy(self, series_id: str) -> MacroObservation:
        if not self._api_key:
            raise RuntimeError(_NO_KEY_ERROR)

        payload = await self._request_observations(
            {
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                # Need ~13 months to compute YoY; fetch extra for missing values ('.').
                "limit": 18,
            }
        )

        return _to_cpi_yoy_observation(series_id, payload)

    def _fetch_vix_level(self) -> float:
        ticker = yf.Ticker(self._vix_symbol)
        history = ticker.history(period="5d")
        if history.empty:
            raise RuntimeError("[FredMacroDataProvider] No VIX data returned by yfinance.")
        return float(history["Close"].iloc[-1])


def _parse_fred_observations(payload: dict[str, Any]) -> list[tuple[datetime, float]]:
    rows: list[tuple[datetime, float]] = []
    for entry in payload.get("observations") or []:
        raw = entry.get("value")
        if raw is None or raw == ".":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        rows.append(
            (
                datetime.strptime(entry["date"], "%Y-%m-%d").replace(tzinfo=UTC),
                value,
            )
        )
    return rows


def _to_observation(series_id: str, payload: dict[str, Any]) -> MacroObservation:
    observations = _parse_fred_observations(payload)
    if not observations:
        raise RuntimeError(
            f"[FredMacroDataProvider] No observations returned by FRED for {series_id!r}."
        )
    as_of, value = observations[0]
    return MacroObservation(series_id=series_id, value=value, as_of=as_of)


def _to_cpi_yoy_observation(series_id: str, payload: dict[str, Any]) -> MacroObservation:
    observations = _parse_fred_observations(payload)
    if len(observations) < 13:
        raise RuntimeError(
            f"[FredMacroDataProvider] Need >=13 CPI observations for YoY; got {len(observations)}."
        )
    as_of, current = observations[0]
    # Observations are newest-first; index 12 is ~12 months earlier for monthly CPI.
    _, year_ago = observations[12]
    if year_ago == 0:
        raise RuntimeError("[FredMacroDataProvider] CPI YoY denominator is zero.")
    yoy_pct = ((current / year_ago) - 1.0) * 100.0
    return MacroObservation(
        series_id=f"{series_id}_YOY",
        value=round(yoy_pct, 2),
        as_of=as_of,
    )
