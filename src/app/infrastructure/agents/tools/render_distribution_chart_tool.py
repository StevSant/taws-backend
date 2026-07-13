from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildDistributionChart
from app.application.quant.unknown_instrument_error import UnknownInstrumentError
from app.domain.charts.entities import ChartConfig
from app.domain.market.errors import MarketDataUnavailableError
from app.infrastructure.agents.tools.market_data_unavailable_message import (
    market_data_unavailable_message,
)


def build_render_distribution_chart_tool(
    build_distribution_chart: BuildDistributionChart, chart_config: ChartConfig
) -> StructuredTool:
    """`render_distribution_chart`: distribution / histogram of daily returns for one instrument.
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
            spec = await build_distribution_chart.execute(instrument_symbol.upper(), timeframe)
        except UnknownInstrumentError as exc:
            return str(exc)
        except MarketDataUnavailableError as exc:
            return market_data_unavailable_message(instrument_symbol.upper(), exc)
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return f"Rendered a daily-return distribution for {spec.meta.symbol}."

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_distribution_chart",
        description=(
            "Render an inline distribution / histogram of daily returns for one instrument, "
            "from real market data. Use when the user asks about the distribution or histogram "
            "of returns."
        ),
        args_schema=_Args,
    )
