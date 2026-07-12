from app.application.charts.downsample_candles import downsample_candles
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
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
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider


class BuildDrawdownChart:
    """Build a drawdown curve: percentage decline from the running peak close, for one
    instrument. Values are <= 0. Real data via `MarketDataProvider`."""

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        chart_config: ChartConfig,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._chart_config = chart_config

    async def execute(self, instrument_symbol: str, timeframe: str) -> ChartSpec:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        days = self._chart_config.days_for(timeframe)
        price_series = await self._market_data_provider.get_price_series(instrument, days)
        candles = downsample_candles(price_series.candles, self._chart_config.max_points)

        points: list[ChartPoint] = []
        peak = float("-inf")
        for candle in candles:
            peak = max(peak, candle.close)
            drawdown_pct = (candle.close - peak) / peak * 100 if peak > 0 else 0.0
            points.append(ChartPoint(x=candle.timestamp.isoformat(), y=round(drawdown_pct, 4)))

        return ChartSpec(
            type=ChartType.DRAWDOWN,
            series=[ChartSeries(name=f"{instrument.symbol} drawdown", points=points)],
            x_axis=ChartAxis(label="Date", type="time"),
            y_axis=ChartAxis(label="Drawdown", type="value", format="percent"),
            meta=ChartMeta(
                title=f"{instrument.symbol} drawdown — {timeframe.upper()}",
                source="market data",
                symbol=instrument.symbol,
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=ChartRequestKind.DRAWDOWN, symbols=[instrument.symbol], timeframe=timeframe
                ),
            ),
        )
