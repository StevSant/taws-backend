from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildMoversChart
from app.domain.charts.entities import ChartSpec
from app.domain.market.entities import AssetClass
from app.infrastructure.agents.tools.resolve_tool_locale import resolve_tool_locale

_DEFAULT_WINDOW_DAYS = 2
_MAX_WINDOW_DAYS = 365


def build_render_market_movers_chart_tool(
    build_movers_chart: BuildMoversChart, default_locale: str
) -> StructuredTool:
    """Build the `render_market_movers_chart` tool: a bar chart of the top gainers/losers.

    Mirrors `render_price_chart` — fetches REAL movers data (reusing the same
    `ListEnrichedInstruments` pipeline as `get_market_movers`), pushes a `bar` `ChartSpec`
    over the SSE custom channel as a side effect, and returns only a one-line text summary to
    the LLM (never the chart JSON). Emits no chart when no instrument has a usable % change."""

    class _Args(BaseModel):
        window_days: int = Field(
            default=_DEFAULT_WINDOW_DAYS,
            description=(
                "Days of price history the ranking covers. Use 2 for 'today's movers', "
                "7 or 30 for weekly/monthly."
            ),
            ge=2,
            le=_MAX_WINDOW_DAYS,
        )
        asset_class: AssetClass | None = Field(
            default=None,
            description=(
                "Optionally restrict the chart to one asset class "
                "(stock, crypto, credit, commodity, forex). Omit to rank everything."
            ),
        )

    async def _run(
        config: RunnableConfig,
        window_days: int = _DEFAULT_WINDOW_DAYS,
        asset_class: AssetClass | None = None,
    ) -> str:
        spec = await build_movers_chart.execute(
            locale=resolve_tool_locale(config, default_locale),
            window_days=window_days,
            asset_class=asset_class,
        )
        if not _has_points(spec):
            return (
                "Market movers are unavailable right now — the upstream price provider "
                "returned no usable data. Tell the user and suggest retrying shortly. Do "
                "NOT invent a ranking."
            )
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return _summarize(spec, window_days)

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_market_movers_chart",
        description=(
            "Render an inline bar chart of the tracked universe's top movers (gainers and "
            "losers) over a window of days, from real market data. Use this whenever the user "
            "asks to see, plot, or visualize 'top movers', 'biggest gainers/losers', or a "
            "market-overview chart. After calling it, briefly describe what it shows."
        ),
        args_schema=_Args,
    )


def _has_points(spec: ChartSpec) -> bool:
    return bool(spec.series and spec.series[0].points)


def _summarize(spec: ChartSpec, window_days: int) -> str:
    points = spec.series[0].points
    top = points[0]
    bottom = points[-1]
    return (
        f"Rendered a top-movers bar chart over {window_days} day(s): "
        f"best {top.x} ({top.y:+.2f}%), worst {bottom.x} ({bottom.y:+.2f}%)."
    )
