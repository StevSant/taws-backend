from app.domain.charts.entities import (
    ChartAxis,
    ChartConfig,
    ChartMeta,
    ChartPoint,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
)
from app.domain.market.entities import MacroObservation, VolatilityRegime
from app.domain.market.ports import MacroDataProvider

# The three series the MacroDataProvider exposes via dedicated methods.
_SUPPORTED_SERIES = {"rates", "cpi", "vix"}


class BuildMacroChart:
    """Build a single-point line chart for one macro series (rates / CPI / VIX).

    Each series has a dedicated `MacroDataProvider` method that returns the latest
    observation — `get_rates()` and `get_cpi()` return a `MacroObservation`
    (series_id, value, as_of), while `get_volatility_regime()` returns a
    `VolatilityRegime` (vix_level, regime, as_of). Both shapes are reduced to a
    single `ChartPoint` (date → value) so the frontend renders them uniformly.

    `series_key` is the friendly key passed by the LLM (e.g. "rates", "cpi", "vix");
    unrecognised keys fall back to "rates". `timeframe` is stored in meta for
    re-request support; the provider always returns the latest reading regardless of
    timeframe (macro observations are single-point snapshots, not time series).
    """

    def __init__(self, macro_data_provider: MacroDataProvider, chart_config: ChartConfig) -> None:
        self._macro_data_provider = macro_data_provider
        self._chart_config = chart_config

    async def execute(self, series_key: str, timeframe: str) -> ChartSpec:
        key = series_key.lower() if series_key.lower() in _SUPPORTED_SERIES else "rates"

        if key == "vix":
            observation = await self._macro_data_provider.get_volatility_regime()
            point = _vix_to_point(observation)
            y_label = "VIX"
        elif key == "cpi":
            observation = await self._macro_data_provider.get_cpi()
            point = _macro_to_point(observation)
            y_label = "CPI"
        else:
            observation = await self._macro_data_provider.get_rates()
            point = _macro_to_point(observation)
            y_label = "Rate (%)"

        return ChartSpec(
            type=ChartType.LINE,
            series=[ChartSeries(name=key.upper(), points=[point])],
            x_axis=ChartAxis(label="Date", type="time"),
            y_axis=ChartAxis(label=y_label, type="value", format="number"),
            meta=ChartMeta(
                title=f"{key.upper()} — {timeframe.upper()}",
                source="FRED / macro",
                symbol=key.upper(),
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=ChartRequestKind.MACRO, symbols=[key], timeframe=timeframe
                ),
            ),
        )


def _macro_to_point(observation: MacroObservation) -> ChartPoint:
    return ChartPoint(x=observation.as_of.isoformat(), y=observation.value)


def _vix_to_point(regime: VolatilityRegime) -> ChartPoint:
    return ChartPoint(x=regime.as_of.isoformat(), y=regime.vix_level)
