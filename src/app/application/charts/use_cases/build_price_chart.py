from datetime import UTC, date, datetime

from app.application.charts.downsample_candles import downsample_candles
from app.application.charts.parse_date_range import parse_date_range
from app.application.charts.resolve_market_source import resolve_market_source
from app.application.charts.slice_candles_by_date_range import slice_candles_by_date_range
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
        market_source_crypto: str,
        market_source_equity: str,
    ) -> None:
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._chart_config = chart_config
        self._market_source_crypto = market_source_crypto
        self._market_source_equity = market_source_equity

    async def execute(
        self,
        instrument_symbol: str,
        timeframe: str,
        chart_type: ChartType = ChartType.CANDLESTICK,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> ChartSpec:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        # A valid custom range wins over the preset: fetch a window wide enough to reach
        # `from_date` (the port fetches by trailing day count only), then slice inclusively.
        # An invalid/partial range degrades to the timeframe preset.
        date_range = parse_date_range(from_date, to_date)
        if date_range is not None:
            start, end = date_range
            days = self._chart_config.fetch_days_for_range(start, datetime.now(UTC).date())
        else:
            days = self._chart_config.days_for(timeframe)

        series = await self._market_data_provider.get_price_series(instrument, days)
        raw_candles = (
            slice_candles_by_date_range(series.candles, date_range[0], date_range[1])
            if date_range is not None
            else series.candles
        )
        candles = downsample_candles(raw_candles, self._chart_config.max_points)

        applied_from, applied_to = _applied_range(date_range)
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
                title=_chart_title(instrument.symbol, timeframe, applied_from, applied_to),
                source=resolve_market_source(
                    instrument.asset_class,
                    self._market_source_crypto,
                    self._market_source_equity,
                ),
                symbol=instrument.symbol,
                timeframe=timeframe,
                timeframes=list(self._chart_config.available_timeframes),
                request=ChartRequest(
                    kind=_CANDLESTICK_KIND if is_candlestick else _LINE_KIND,
                    symbols=[instrument.symbol],
                    timeframe=timeframe,
                    from_date=applied_from,
                    to_date=applied_to,
                ),
            ),
        )


def _applied_range(date_range: tuple[date, date] | None) -> tuple[str | None, str | None]:
    """Echo the applied custom range as ISO strings, or `(None, None)` for a preset render."""
    if date_range is None:
        return None, None
    start, end = date_range
    return start.isoformat(), end.isoformat()


def _chart_title(symbol: str, timeframe: str, from_date: str | None, to_date: str | None) -> str:
    """Title reflects a custom range when applied, otherwise the timeframe preset label."""
    if from_date and to_date:
        return f"{symbol} — {from_date} → {to_date}"
    return f"{symbol} — {timeframe.upper()}"


def _to_bar(candle: PriceCandle) -> OhlcBar:
    return OhlcBar(
        t=candle.timestamp.isoformat(),
        o=candle.open,
        h=candle.high,
        l=candle.low,
        c=candle.close,
        v=candle.volume,
    )
