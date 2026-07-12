from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildDrawdownChart
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.charts.entities import ChartConfig


def build_render_drawdown_chart_tool(
    build_drawdown_chart: BuildDrawdownChart, chart_config: ChartConfig
) -> StructuredTool:
    """`render_drawdown_chart`: drawdown / decline from peak for one instrument.
    Emits the chart over the SSE custom channel; returns a one-line summary to the LLM."""

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

    async def _run(
        instrument_symbol: str,
        timeframe: str = chart_config.default_timeframe,
    ) -> str:
        try:
            spec = await build_drawdown_chart.execute(instrument_symbol.upper(), timeframe)
        except UnknownInstrumentError as exc:
            return str(exc)
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return f"Rendered a {spec.meta.timeframe} drawdown chart for {spec.meta.symbol}."

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_drawdown_chart",
        description=(
            "Render an inline chart showing the drawdown / decline from peak (max drawdown) "
            "for one instrument, from real market data. Use when the user asks about drawdown "
            "or decline from peak."
        ),
        args_schema=_Args,
    )
