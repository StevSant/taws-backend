from datetime import UTC, datetime

from app.domain.market.entities import MacroObservation, VolatilityRegime
from app.domain.market.ports import MacroDataProvider
from app.infrastructure.macro.bucket_volatility_regime import bucket_volatility_regime


class FixtureMacroDataProvider(MacroDataProvider):
    """MacroDataProvider fallback: static, plausible macro figures from `Settings`.

    Used by `RoutingMacroDataProvider` whenever `FRED_API_KEY` is unset or a live FRED/VIX call
    fails, so macro-aware signals/scenarios stay available in dev without any API key —
    consistent with `FixtureNewsProvider`/`FixtureMarketDataProvider`.
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
    ) -> None:
        self._rates_series_id = rates_series_id
        self._cpi_series_id = cpi_series_id
        self._fixture_rate = fixture_rate
        self._fixture_cpi = fixture_cpi
        self._fixture_vix = fixture_vix
        self._low_threshold = low_threshold
        self._elevated_threshold = elevated_threshold
        self._high_threshold = high_threshold

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
