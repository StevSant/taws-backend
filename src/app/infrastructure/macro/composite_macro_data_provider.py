from app.domain.market.entities import (
    MacroIndicator,
    MacroObservation,
    MacroSeries,
    VolatilityRegime,
)
from app.domain.market.ports import MacroDataProvider
from app.infrastructure.macro.yfinance_gold_series_source import YFinanceGoldSeriesSource


class CompositeMacroDataProvider(MacroDataProvider):
    """Selects the data *source* per macro concern, then delegates.

    Rates, CPI and the oil/10Y `get_indicator_history` series come from FRED; the gold history
    series comes from yfinance (`GC=F`) because FRED's free gold fixing was discontinued (see
    `YFinanceGoldSeriesSource`). VIX already comes from yfinance *inside* `FredMacroDataProvider`,
    so `get_volatility_regime` still routes there unchanged.

    This is source selection only. Error handling stays in `RoutingMacroDataProvider`, which
    wraps this composite as its `live_provider` and maps any failure — including the discontinued
    series case — to `MacroDataUnavailableError` (a 503) instead of a fabricated figure.
    """

    def __init__(
        self,
        fred_provider: MacroDataProvider,
        gold_source: YFinanceGoldSeriesSource,
    ) -> None:
        self._fred_provider = fred_provider
        self._gold_source = gold_source

    async def get_rates(self) -> MacroObservation:
        return await self._fred_provider.get_rates()

    async def get_cpi(self) -> MacroObservation:
        return await self._fred_provider.get_cpi()

    async def get_volatility_regime(self) -> VolatilityRegime:
        return await self._fred_provider.get_volatility_regime()

    async def get_indicator_history(self, indicator: MacroIndicator, days: int) -> MacroSeries:
        if indicator is MacroIndicator.GOLD:
            return await self._gold_source.get_series(days)
        return await self._fred_provider.get_indicator_history(indicator, days)
