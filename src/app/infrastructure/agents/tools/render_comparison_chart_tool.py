from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec, summarize_comparison_chart
from app.application.charts.use_cases import BuildComparisonChart
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.charts.entities import ChartConfig
from app.domain.market.errors import MarketDataUnavailableError
from app.infrastructure.agents.tools.market_data_unavailable_message import (
    market_data_unavailable_message,
)


def build_render_comparison_chart_tool(
    build_comparison_chart: BuildComparisonChart, chart_config: ChartConfig
) -> StructuredTool:
    """`render_comparison_chart`: overlay several instruments rebased to 100 for comparison.
    Emits the chart over the SSE custom channel; returns a one-line summary to the LLM."""

    class _Args(BaseModel):
        instrument_symbols: list[str] = Field(
            description="Two or more instrument symbols to compare, e.g. ['BTC','ETH','SPY']."
        )
        timeframe: str = Field(
            default=chart_config.default_timeframe,
            description="Timeframe label: " + ", ".join(chart_config.available_timeframes) + ".",
        )

    async def _run(
        instrument_symbols: list[str], timeframe: str = chart_config.default_timeframe
    ) -> str:
        try:
            spec = await build_comparison_chart.execute(
                [symbol.upper() for symbol in instrument_symbols], timeframe
            )
        except UnknownInstrumentError as exc:
            return str(exc)
        except MarketDataUnavailableError as exc:
            # No chart: one missing leg makes the whole rebased comparison a lie.
            return market_data_unavailable_message(exc.symbol, exc)
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return summarize_comparison_chart(spec)

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_comparison_chart",
        description=(
            "Render an inline chart comparing several instruments' price performance, "
            "rebased to 100 at the start of the window, from real market data. Use whenever "
            "the turn compares, contrasts, or ranks two or more assets — including implicit "
            "comparisons like 'how do NVDA and AAPL compare this quarter', not only when the "
            "user literally says 'chart', 'graph', or 'gráficamente'."
        ),
        args_schema=_Args,
    )
