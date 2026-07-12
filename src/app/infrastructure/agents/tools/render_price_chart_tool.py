from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildPriceChart
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.charts.entities import ChartConfig, ChartSpec, ChartType

_CANDLESTICK = "candlestick"
_LINE = "line"


def build_render_price_chart_tool(
    build_price_chart: BuildPriceChart, chart_config: ChartConfig
) -> StructuredTool:
    """Build the `render_price_chart` tool: fetches REAL OHLC data and pushes a chart to
    the chat as a side effect, returning only a short text summary to the LLM.

    The chart itself is emitted over the LangGraph `custom` channel via
    `get_stream_writer()` (the same channel `specialist_node_factory` uses for traces),
    tagged `{"kind": "chart"}` so `LangGraphAgentRunner` routes it to a `ChartEvent`. The
    tool's *return value* is deliberately a one-line summary, NOT the chart JSON — feeding
    the full series back into the model would bloat context and risk it echoing raw data."""

    class _Args(BaseModel):
        instrument_symbol: str = Field(
            description="Instrument symbol to chart, e.g. BTC, AAPL, ETH."
        )
        timeframe: str = Field(
            default=chart_config.default_timeframe,
            description=(
                "Timeframe label. One of: " + ", ".join(chart_config.available_timeframes) + "."
            ),
        )
        chart_type: str = Field(
            default=_CANDLESTICK,
            description='Either "candlestick" (OHLC) or "line" (close price).',
        )

    async def _run(
        instrument_symbol: str,
        timeframe: str = chart_config.default_timeframe,
        chart_type: str = _CANDLESTICK,
    ) -> str:
        resolved_type = ChartType.LINE if chart_type == _LINE else ChartType.CANDLESTICK
        try:
            spec = await build_price_chart.execute(
                instrument_symbol.upper(), timeframe, resolved_type
            )
        except UnknownInstrumentError as exc:
            return str(exc)

        writer = get_stream_writer()
        writer({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return _summarize(spec)

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_price_chart",
        description=(
            "Render an inline price chart (candlestick or line) for one instrument over a "
            "timeframe, from real market data. Call this whenever the user asks to see, "
            "plot, chart, or visualize an instrument's price or price history. After "
            "calling it, briefly describe what the chart shows — do not restate the raw "
            "numbers."
        ),
        args_schema=_Args,
    )


def _summarize(spec: ChartSpec) -> str:
    series = spec.series[0] if spec.series else None
    if series and series.bars:
        first, last = series.bars[0], series.bars[-1]
        change = _pct(first.c, last.c)
        return (
            f"Rendered a {spec.meta.timeframe} candlestick chart for {spec.meta.symbol}: "
            f"latest close {last.c:.4g}{change}."
        )
    if series and series.points:
        first, last = series.points[0], series.points[-1]
        change = _pct(first.y, last.y)
        return (
            f"Rendered a {spec.meta.timeframe} price line for {spec.meta.symbol}: "
            f"latest {last.y:.4g}{change}."
        )
    return f"Rendered a chart for {spec.meta.symbol}."


def _pct(first: float, last: float) -> str:
    if first == 0:
        return ""
    return f" ({(last - first) / first * 100:+.2f}% over the window)"
