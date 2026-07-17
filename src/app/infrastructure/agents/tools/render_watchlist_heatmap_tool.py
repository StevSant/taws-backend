from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from app.application.charts import serialize_chart_spec
from app.application.charts.use_cases import BuildWatchlistHeatmap
from app.domain.charts.entities import ChartSpec
from app.infrastructure.agents.tools.resolve_tool_user_id import resolve_tool_user_id


class _RenderWatchlistHeatmapArgs(BaseModel):
    """No arguments: the acting user comes from the injected config, never from the model."""


def build_render_watchlist_heatmap_tool(
    build_watchlist_heatmap: BuildWatchlistHeatmap,
) -> StructuredTool:
    """Build the `render_watchlist_heatmap` tool: a heatmap of the user's OWN watchlist.

    The per-user sibling of `render_market_movers_chart`. SECURITY: the acting user id comes
    from the turn's `RunnableConfig` (`resolve_tool_user_id`), where `LangGraphAgentRunner`
    put the verified JWT's id — NEVER a model-supplied argument — so a turn can only ever
    heatmap the authenticated user's own watchlists. Pushes a `heatmap` `ChartSpec` over the
    SSE custom channel and returns a one-line summary; emits no chart when the user tracks
    nothing (or no symbol has usable price data)."""

    async def _run(config: RunnableConfig) -> str:
        user_id = resolve_tool_user_id(config)
        if user_id is None:
            return (
                "No authenticated user is attached to this conversation, so a watchlist "
                "heatmap cannot be built. Tell the user to sign in and retry."
            )

        spec = await build_watchlist_heatmap.execute(user_id)
        if not spec.cells:
            return (
                "The user has no watchlist instruments with usable price data to chart. "
                "Suggest adding instruments to a watchlist first. Do NOT invent values."
            )
        get_stream_writer()({"kind": "chart", "chart": serialize_chart_spec(spec)})
        return _summarize(spec)

    return StructuredTool.from_function(
        coroutine=_run,
        name="render_watchlist_heatmap",
        description=(
            "Render an inline heatmap of the user's OWN watchlist, one tile per tracked "
            "instrument colored by its recent % change, from real market data. Use this "
            "whenever the user asks to see, plot, or visualize how 'my watchlist', 'my "
            "assets', or 'my portfolio' is doing as a heatmap. After calling it, briefly "
            "describe what it shows."
        ),
        args_schema=_RenderWatchlistHeatmapArgs,
    )


def _summarize(spec: ChartSpec) -> str:
    cells = spec.cells or []
    gainers = sum(1 for cell in cells if cell.value > 0)
    losers = sum(1 for cell in cells if cell.value < 0)
    return (
        f"Rendered a watchlist heatmap of {len(cells)} instrument(s): {gainers} up, {losers} down."
    )
