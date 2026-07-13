from typing import Any

from app.application.charts import serialize_chart_spec
from app.domain.charts.entities import ChartSpec, ChartType
from app.infrastructure.realtime.tools.args.render_chart_args import (
    RenderComparisonChartArgs,
    RenderDistributionChartArgs,
    RenderDrawdownChartArgs,
    RenderMacroChartArgs,
    RenderPriceChartArgs,
)


def _ensure_charts_enabled(container: Any) -> None:
    if not getattr(container._settings, "charts_enabled", True):
        raise RuntimeError("Chart tools are disabled")


def _result(summary: str, spec: ChartSpec) -> dict[str, Any]:
    return {"summary": summary, "chart": serialize_chart_spec(spec)}


async def handle_render_price_chart(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    typed: RenderPriceChartArgs = args
    chart_type = ChartType.LINE if typed.chart_type == "line" else ChartType.CANDLESTICK
    spec = await container.get_build_price_chart_use_case().execute(
        typed.instrument_symbol.upper(), typed.timeframe, chart_type
    )
    return _result(_summarize_price(spec), spec)


async def handle_render_comparison_chart(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    typed: RenderComparisonChartArgs = args
    spec = await container.get_build_comparison_chart_use_case().execute(
        [symbol.upper() for symbol in typed.instrument_symbols], typed.timeframe
    )
    names = ", ".join(series.name for series in spec.series)
    return _result(f"Rendered a {spec.meta.timeframe} rebased comparison of {names}.", spec)


async def handle_render_macro_chart(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    typed: RenderMacroChartArgs = args
    spec = await container.get_build_macro_chart_use_case().execute(
        typed.series_key, typed.timeframe
    )
    return _result(f"Rendered a {spec.meta.timeframe} chart of {spec.meta.symbol}.", spec)


async def handle_render_drawdown_chart(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    typed: RenderDrawdownChartArgs = args
    spec = await container.get_build_drawdown_chart_use_case().execute(
        typed.instrument_symbol.upper(), typed.timeframe
    )
    return _result(
        f"Rendered a {spec.meta.timeframe} drawdown chart for {spec.meta.symbol}.",
        spec,
    )


async def handle_render_distribution_chart(
    container: Any, args: Any, user_id: str
) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    typed: RenderDistributionChartArgs = args
    spec = await container.get_build_distribution_chart_use_case().execute(
        typed.instrument_symbol.upper(), typed.timeframe
    )
    return _result(f"Rendered a daily-return distribution for {spec.meta.symbol}.", spec)


async def handle_render_sentiment_gauge(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    _ensure_charts_enabled(container)
    spec = await container.get_build_sentiment_gauge_use_case().execute()
    return _result(spec.meta.title, spec)


def _summarize_price(spec: ChartSpec) -> str:
    series = spec.series[0] if spec.series else None
    if series and series.bars:
        first, last = series.bars[0], series.bars[-1]
        return (
            f"Rendered a {spec.meta.timeframe} candlestick chart for "
            f"{spec.meta.symbol}: latest close {last.c:.4g}{_pct(first.c, last.c)}."
        )
    if series and series.points:
        first, last = series.points[0], series.points[-1]
        return (
            f"Rendered a {spec.meta.timeframe} price line for {spec.meta.symbol}: "
            f"latest {last.y:.4g}{_pct(first.y, last.y)}."
        )
    return f"Rendered a chart for {spec.meta.symbol}."


def _pct(first: float, last: float) -> str:
    if first == 0:
        return ""
    return f" ({(last - first) / first * 100:+.2f}% over the window)"
