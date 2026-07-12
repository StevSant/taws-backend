from app.application.charts.downsample_candles import downsample_candles
from app.application.quant.compute_daily_returns import compute_daily_returns
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

_BUCKET_COUNT = 21


class BuildDistributionChart:
    """Build a histogram of daily returns (%) for one instrument over a window — a
    distribution chart rendered as bars. Reuses `compute_daily_returns` for the returns."""

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
        returns = [pct for _, pct in compute_daily_returns(candles)]

        points = _histogram(returns)

        return ChartSpec(
            type=ChartType.DISTRIBUTION,
            series=[ChartSeries(name=f"{instrument.symbol} daily returns", points=points)],
            x_axis=ChartAxis(label="Daily return %", type="category"),
            y_axis=ChartAxis(label="Days", type="value", format="number"),
            meta=ChartMeta(
                title=f"{instrument.symbol} return distribution — {timeframe.upper()}",
                source="market data",
                symbol=instrument.symbol,
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=ChartRequestKind.DISTRIBUTION,
                    symbols=[instrument.symbol],
                    timeframe=timeframe,
                ),
            ),
        )


def _histogram(returns: list[float]) -> list[ChartPoint]:
    if not returns:
        return []
    low, high = min(returns), max(returns)
    if low == high:
        return [ChartPoint(x=f"{low:.2f}", y=float(len(returns)))]
    width = (high - low) / _BUCKET_COUNT
    counts = [0] * _BUCKET_COUNT
    for value in returns:
        index = min(int((value - low) / width), _BUCKET_COUNT - 1)
        counts[index] += 1
    return [
        ChartPoint(x=f"{low + (index + 0.5) * width:.2f}", y=float(count))
        for index, count in enumerate(counts)
    ]
