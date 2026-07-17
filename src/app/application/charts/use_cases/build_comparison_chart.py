from app.application.charts.downsample_candles import downsample_candles
from app.application.charts.resolve_market_source import resolve_market_source
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


class BuildComparisonChart:
    """Build a multi-series comparison chart with each instrument's close rebased to 100 at
    the window start — so assets on different price scales are visually comparable. Real
    data via `MarketDataProvider`; unknown symbols are skipped (at least one required)."""

    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        chart_config: ChartConfig,
        market_source_crypto: str,
        market_source_equity: str,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._chart_config = chart_config
        self._market_source_crypto = market_source_crypto
        self._market_source_equity = market_source_equity

    async def execute(self, instrument_symbols: list[str], timeframe: str) -> ChartSpec:
        days = self._chart_config.days_for(timeframe)
        series_list: list[ChartSeries] = []
        resolved_symbols: list[str] = []
        sources: dict[str, None] = {}  # insertion-ordered set of the vendors actually charted

        for symbol in instrument_symbols:
            instrument = self._instrument_universe.by_symbol(symbol)
            if instrument is None:
                continue
            price_series = await self._market_data_provider.get_price_series(instrument, days)
            candles = downsample_candles(price_series.candles, self._chart_config.max_points)
            if not candles or candles[0].close == 0:
                continue
            base = candles[0].close
            series_list.append(
                ChartSeries(
                    name=instrument.symbol,
                    points=[
                        ChartPoint(x=candle.timestamp.isoformat(), y=candle.close / base * 100)
                        for candle in candles
                    ],
                )
            )
            resolved_symbols.append(instrument.symbol)
            sources[
                resolve_market_source(
                    instrument.asset_class,
                    self._market_source_crypto,
                    self._market_source_equity,
                )
            ] = None

        if not resolved_symbols:
            raise UnknownInstrumentError(", ".join(instrument_symbols))

        return ChartSpec(
            type=ChartType.COMPARISON,
            series=series_list,
            x_axis=ChartAxis(label="Date", type="time"),
            y_axis=ChartAxis(label="Rebased to 100", type="value", format="number"),
            meta=ChartMeta(
                title=f"{' vs '.join(resolved_symbols)} — {timeframe.upper()} (rebased)",
                # Mixed-asset comparisons (e.g. BTC vs SPY) cite every vendor that priced a leg.
                source=" / ".join(sources),
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=ChartRequestKind.COMPARISON, symbols=resolved_symbols, timeframe=timeframe
                ),
            ),
        )
