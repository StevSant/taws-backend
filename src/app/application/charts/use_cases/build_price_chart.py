from app.application.charts.downsample_candles import downsample_candles
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.charts.entities import (
    ChartAxis,
    ChartConfig,
    ChartMeta,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
    OhlcBar,
)
from app.domain.charts.entities.chart_point import ChartPoint
from app.domain.market.entities import PriceCandle
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider

_CANDLESTICK_KIND = ChartRequestKind.PRICE_CANDLESTICK
_LINE_KIND = ChartRequestKind.PRICE_LINE


class BuildPriceChart:
    """Build a price `ChartSpec` (candlestick or line) for one instrument over a timeframe.

    Mirrors `ComputeMarketStats`: resolves the symbol via `InstrumentUniverse`, fetches the
    OHLC series via `MarketDataProvider.get_price_series`, and derives a chart from REAL
    data (never LLM-authored). Reused by the `render_price_chart` tool and, later,
    `POST /charts/render`. Raises `UnknownInstrumentError` for an unknown symbol; thin data
    still renders (fewer points)."""

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        chart_config: ChartConfig,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._chart_config = chart_config

    async def execute(
        self, instrument_symbol: str, timeframe: str, chart_type: ChartType = ChartType.CANDLESTICK
    ) -> ChartSpec:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        days = self._chart_config.days_for(timeframe)
        series = await self._market_data_provider.get_price_series(instrument, days)
        candles = downsample_candles(series.candles, self._chart_config.max_points)

        is_candlestick = chart_type is ChartType.CANDLESTICK
        chart_series = (
            ChartSeries(name=instrument.symbol, bars=[_to_bar(candle) for candle in candles])
            if is_candlestick
            else ChartSeries(
                name=instrument.symbol,
                points=[
                    ChartPoint(x=candle.timestamp.isoformat(), y=candle.close) for candle in candles
                ],
            )
        )

        return ChartSpec(
            type=chart_type,
            series=[chart_series],
            x_axis=ChartAxis(label="Date", type="time"),
            y_axis=ChartAxis(
                label=f"Price ({instrument.currency})", type="value", format="currency"
            ),
            meta=ChartMeta(
                title=f"{instrument.symbol} — {timeframe.upper()}",
                source="market data",
                symbol=instrument.symbol,
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=_CANDLESTICK_KIND if is_candlestick else _LINE_KIND,
                    symbols=[instrument.symbol],
                    timeframe=timeframe,
                ),
            ),
        )


def _to_bar(candle: PriceCandle) -> OhlcBar:
    return OhlcBar(
        t=candle.timestamp.isoformat(),
        o=candle.open,
        h=candle.high,
        l=candle.low,
        c=candle.close,
        v=candle.volume,
    )
