from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildMacroChart
from app.domain.charts.entities import ChartConfig


def build_render_macro_chart_tool(
    build_macro_chart: BuildMacroChart, chart_config: ChartConfig
) -> StructuredTool:
    """`render_macro_chart`: macro series (interest rates, CPI, or VIX volatility).
    Emits the chart over the SSE custom channel; returns a one-line summary to the LLM."""

    class _Args(BaseModel):
        series_key: str = Field(
            default="rates",
            description="Macro series to chart. One of: rates, cpi, vix.",
        )
        timeframe: str = Field(
            default=chart_config.default_timeframe,
            description=(
                "Timeframe label. One of: " + ", ".join(chart_config.available_timeframes) + "."
            ),
        )

    async def _run(
        series_key: str = "rates",
        timeframe: str = chart_config.default_timeframe,
    ) -> str:
        spec = await build_macro_chart.execute(series_key, timeframe)
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return f"Rendered a {spec.meta.timeframe} chart of {spec.meta.symbol}."

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_macro_chart",
        description=(
            "Render an inline chart of a macro series (interest rates, CPI, or VIX volatility), "
            "from real macro data. Use when the user asks to see rates, inflation/CPI, or "
            "volatility/VIX."
        ),
        args_schema=_Args,
    )
