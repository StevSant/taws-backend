import math
from datetime import UTC, datetime, timedelta

from app.domain.market.entities import (
    MacroIndicator,
    MacroObservation,
    MacroSeries,
    VolatilityRegime,
)
from app.domain.market.ports import MacroDataProvider
from app.infrastructure.macro.bucket_volatility_regime import bucket_volatility_regime

# Peak-to-trough wobble of the synthetic history, as a fraction of the base value — enough
# for a sparkline to read as "moving" without implying a real trend.
_FIXTURE_SERIES_AMPLITUDE = 0.03


class FixtureMacroDataProvider(MacroDataProvider):
    """MacroDataProvider fallback: static, plausible macro figures from `Settings`.

    Used by `RoutingMacroDataProvider` whenever `FRED_API_KEY` is unset or a live FRED/VIX call
    fails, so macro-aware signals/scenarios stay available in dev without any API key —
    consistent with `FixtureNewsProvider`/`FixtureMarketDataProvider`. `get_indicator_history`
    synthesizes a deterministic gently-oscillating series that ends exactly at the indicator's
    fixture value, so sparklines have something to draw offline.
    """

    def __init__(
        self,
        rates_series_id: str,
        cpi_series_id: str,
        fixture_rate: float,
        fixture_cpi: float,
        fixture_vix: float,
        low_threshold: float,
        elevated_threshold: float,
        high_threshold: float,
        indicator_series_ids: dict[MacroIndicator, str],
        indicator_fixture_values: dict[MacroIndicator, float],
    ) -> None:
        self._rates_series_id = rates_series_id
        self._cpi_series_id = cpi_series_id
        self._fixture_rate = fixture_rate
        self._fixture_cpi = fixture_cpi
        self._fixture_vix = fixture_vix
        self._low_threshold = low_threshold
        self._elevated_threshold = elevated_threshold
        self._high_threshold = high_threshold
        self._indicator_series_ids = indicator_series_ids
        self._indicator_fixture_values = indicator_fixture_values

    async def get_rates(self) -> MacroObservation:
        return MacroObservation(
            series_id=self._rates_series_id, value=self._fixture_rate, as_of=datetime.now(UTC)
        )

    async def get_cpi(self) -> MacroObservation:
        return MacroObservation(
            series_id=self._cpi_series_id, value=self._fixture_cpi, as_of=datetime.now(UTC)
        )

    async def get_volatility_regime(self) -> VolatilityRegime:
        regime = bucket_volatility_regime(
            self._fixture_vix, self._low_threshold, self._elevated_threshold, self._high_threshold
        )
        return VolatilityRegime(vix_level=self._fixture_vix, regime=regime, as_of=datetime.now(UTC))

    async def get_indicator_history(self, indicator: MacroIndicator, days: int) -> MacroSeries:
        base = self._indicator_fixture_values.get(indicator)
        if base is None:
            raise RuntimeError(
                f"[FixtureMacroDataProvider] No fixture value configured for {indicator!r}."
            )
        series_id = self._indicator_series_ids.get(indicator, indicator.value)
        observations = _synthesize_history(series_id, base, max(days, 1))
        return MacroSeries(indicator=indicator, series_id=series_id, observations=observations)


def _synthesize_history(series_id: str, base: float, days: int) -> list[MacroObservation]:
    """Deterministic daily series (oldest -> newest) oscillating around and ending at `base`."""
    now = datetime.now(UTC)
    span = max(days - 1, 1)
    observations: list[MacroObservation] = []
    for index in range(days):
        as_of = now - timedelta(days=span - index)
        factor = 1 + _FIXTURE_SERIES_AMPLITUDE * math.sin((index / span) * math.tau)
        observations.append(
            MacroObservation(series_id=series_id, value=round(base * factor, 4), as_of=as_of)
        )
    observations[-1] = MacroObservation(series_id=series_id, value=base, as_of=now)
    return observations
