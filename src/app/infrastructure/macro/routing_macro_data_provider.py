import logging

from app.domain.market.entities import (
    MacroIndicator,
    MacroObservation,
    MacroSeries,
    VolatilityRegime,
)
from app.domain.market.ports import MacroDataProvider

logger = logging.getLogger(__name__)


class RoutingMacroDataProvider(MacroDataProvider):
    """MacroDataProvider that prefers the live FRED/VIX adapter and falls back to fixtures.

    Any exception from the live adapter — including "no `FRED_API_KEY` configured" — falls back
    to the deterministic `FixtureMacroDataProvider`, per method. Per-method (not all-or-nothing)
    so a live VIX fetch succeeding while FRED rates/CPI are unavailable (no key) still returns
    real volatility data alongside fixture rates/CPI, mirroring `RoutingMarketDataProvider`'s
    per-call fallback shape.
    """

    def __init__(
        self, live_provider: MacroDataProvider, fixture_provider: MacroDataProvider
    ) -> None:
        self._live_provider = live_provider
        self._fixture_provider = fixture_provider

    async def get_rates(self) -> MacroObservation:
        try:
            return await self._live_provider.get_rates()
        except Exception:
            logger.warning("Live FRED rates lookup failed; using fixture.", exc_info=True)
            return await self._fixture_provider.get_rates()

    async def get_cpi(self) -> MacroObservation:
        try:
            return await self._live_provider.get_cpi()
        except Exception:
            logger.warning("Live FRED CPI lookup failed; using fixture.", exc_info=True)
            return await self._fixture_provider.get_cpi()

    async def get_volatility_regime(self) -> VolatilityRegime:
        try:
            return await self._live_provider.get_volatility_regime()
        except Exception:
            logger.warning("Live VIX lookup failed; using fixture.", exc_info=True)
            return await self._fixture_provider.get_volatility_regime()

    async def get_indicator_history(self, indicator: MacroIndicator, days: int) -> MacroSeries:
        try:
            return await self._live_provider.get_indicator_history(indicator, days)
        except Exception:
            logger.warning(
                "Live FRED history for %s failed; using fixture.", indicator, exc_info=True
            )
            return await self._fixture_provider.get_indicator_history(indicator, days)
