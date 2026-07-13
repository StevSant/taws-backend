import logging

from app.domain.market.entities import (
    MacroIndicator,
    MacroObservation,
    MacroSeries,
    VolatilityRegime,
)
from app.domain.market.errors import MacroDataUnavailableError
from app.domain.market.ports import MacroDataProvider

logger = logging.getLogger(__name__)


class RoutingMacroDataProvider(MacroDataProvider):
    """MacroDataProvider fronting the live FRED/VIX adapter. Real observations, or an error.

    This used to fall back, per method, to a `FixtureMacroDataProvider` on ANY exception —
    including "no `FRED_API_KEY` configured", which is not an outage but a misconfiguration
    that would then never be noticed, because the macro specialist just kept answering with
    confident invented rates and CPI prints.

    Still per-method: a live VIX fetch succeeding while FRED is down should still yield a real
    volatility regime — they're independent sources, and one being unavailable is no reason to
    withhold the other. What changed is only what happens on failure.
    """

    def __init__(self, live_provider: MacroDataProvider) -> None:
        self._live_provider = live_provider

    async def get_rates(self) -> MacroObservation:
        try:
            return await self._live_provider.get_rates()
        except Exception as error:
            logger.warning("Live FRED rates lookup failed.", exc_info=True)
            raise MacroDataUnavailableError("policy rates", str(error)) from error

    async def get_cpi(self) -> MacroObservation:
        try:
            return await self._live_provider.get_cpi()
        except Exception as error:
            logger.warning("Live FRED CPI lookup failed.", exc_info=True)
            raise MacroDataUnavailableError("CPI", str(error)) from error

    async def get_volatility_regime(self) -> VolatilityRegime:
        try:
            return await self._live_provider.get_volatility_regime()
        except Exception as error:
            logger.warning("Live VIX lookup failed.", exc_info=True)
            raise MacroDataUnavailableError("volatility regime", str(error)) from error

    async def get_indicator_history(self, indicator: MacroIndicator, days: int) -> MacroSeries:
        try:
            return await self._live_provider.get_indicator_history(indicator, days)
        except Exception as error:
            logger.warning("Live FRED history for %s failed.", indicator, exc_info=True)
            raise MacroDataUnavailableError(str(indicator), str(error)) from error
