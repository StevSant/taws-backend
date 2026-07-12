from typing import Any

from app.infrastructure.realtime.tools.args import (
    GenerateSignalArgs,
    GetMarketDataArgs,
    GetNewsArgs,
    GetNotesArgs,
    GetWatchlistArgs,
    ListSignalsArgs,
    RenderComparisonChartArgs,
    RenderDistributionChartArgs,
    RenderDrawdownChartArgs,
    RenderMacroChartArgs,
    RenderPriceChartArgs,
    RenderSentimentGaugeArgs,
)
from app.infrastructure.realtime.tools.handlers import (
    handle_generate_signal,
    handle_get_market_data,
    handle_get_news,
    handle_get_notes,
    handle_get_watchlist,
    handle_list_signals,
    handle_render_comparison_chart,
    handle_render_distribution_chart,
    handle_render_drawdown_chart,
    handle_render_macro_chart,
    handle_render_price_chart,
    handle_render_sentiment_gauge,
)
from app.infrastructure.realtime.tools.realtime_tool import RealtimeTool
from app.infrastructure.realtime.tools.tool_not_found_error import ToolNotFoundError

# The single source of truth for which realtime tools exist and how each is validated +
# dispatched. Adding a tool = add one `RealtimeTool` here (plus its arg model + handler);
# the schema list, the allowlist, and dispatch all derive from this dict, so they can't
# drift apart.
_REALTIME_TOOLS: dict[str, RealtimeTool] = {
    "get_market_data": RealtimeTool(
        name="get_market_data",
        description=(
            "Get the latest price and a recent daily price series for one tracked "
            "instrument (stock, crypto, commodity, or forex) by its symbol."
        ),
        args_model=GetMarketDataArgs,
        handler=handle_get_market_data,
    ),
    "get_news": RealtimeTool(
        name="get_news",
        description=(
            "Get recent market news, optionally scoped to one instrument symbol. Each "
            "item includes its source and publication date."
        ),
        args_model=GetNewsArgs,
        handler=handle_get_news,
    ),
    "list_signals": RealtimeTool(
        name="list_signals",
        description=(
            "List the Analyst's recorded impact signals (impact class, confidence, "
            "thesis) for one instrument symbol."
        ),
        args_model=ListSignalsArgs,
        handler=handle_list_signals,
    ),
    "generate_signal": RealtimeTool(
        name="generate_signal",
        description=(
            "Run the Analyst pipeline on demand for one instrument and return the newly "
            "generated impact signal. Slower than list_signals — acknowledge before calling."
        ),
        args_model=GenerateSignalArgs,
        handler=handle_generate_signal,
    ),
    "get_watchlist": RealtimeTool(
        name="get_watchlist",
        description=(
            "Get the current user's own watchlists and the instruments tracked in each. "
            "Takes no arguments — always scoped to the authenticated user. Use when they "
            "ask about 'my watchlist' or what they are tracking."
        ),
        args_model=GetWatchlistArgs,
        handler=handle_get_watchlist,
    ),
    "get_notes": RealtimeTool(
        name="get_notes",
        description=(
            "Get the current user's own saved notes, most-recent first. Takes no arguments "
            "— always scoped to the authenticated user. Use when they ask about 'my notes' "
            "or what they wrote down."
        ),
        args_model=GetNotesArgs,
        handler=handle_get_notes,
    ),
    "render_price_chart": RealtimeTool(
        name="render_price_chart",
        description=(
            "Display an interactive candlestick or line price chart directly on the user's "
            "current voice screen. Use when the user asks to see, plot, chart, generate, "
            "create, or visualize price history; this tool is the visual capability."
        ),
        args_model=RenderPriceChartArgs,
        handler=handle_render_price_chart,
    ),
    "render_comparison_chart": RealtimeTool(
        name="render_comparison_chart",
        description=(
            "Display an interactive comparison chart directly on the user's current voice "
            "screen, with instruments rebased to 100. Use for visual comparisons, overlays, "
            "or contrasting asset performance."
        ),
        args_model=RenderComparisonChartArgs,
        handler=handle_render_comparison_chart,
    ),
    "render_macro_chart": RealtimeTool(
        name="render_macro_chart",
        description=(
            "Display an interactive macro chart directly on the user's current voice screen "
            "for rates, CPI, or VIX. Use for interest rates, inflation, or volatility."
        ),
        args_model=RenderMacroChartArgs,
        handler=handle_render_macro_chart,
    ),
    "render_drawdown_chart": RealtimeTool(
        name="render_drawdown_chart",
        description=(
            "Display an interactive drawdown chart directly on the user's current voice "
            "screen. Use for loss-from-peak or downside-risk questions."
        ),
        args_model=RenderDrawdownChartArgs,
        handler=handle_render_drawdown_chart,
    ),
    "render_distribution_chart": RealtimeTool(
        name="render_distribution_chart",
        description=(
            "Display an interactive return histogram directly on the user's current voice "
            "screen. Use for distribution, dispersion, or tail-behavior questions."
        ),
        args_model=RenderDistributionChartArgs,
        handler=handle_render_distribution_chart,
    ),
    "render_sentiment_gauge": RealtimeTool(
        name="render_sentiment_gauge",
        description=(
            "Display the interactive Crypto Fear & Greed gauge directly on the user's "
            "current voice screen. Use for market sentiment or Fear & Greed requests."
        ),
        args_model=RenderSentimentGaugeArgs,
        handler=handle_render_sentiment_gauge,
    ),
}

_CHART_TOOL_NAMES = {
    "render_price_chart",
    "render_comparison_chart",
    "render_macro_chart",
    "render_drawdown_chart",
    "render_distribution_chart",
    "render_sentiment_gauge",
}


def _is_session_tool_enabled(name: str, *, charts_enabled: bool) -> bool:
    if charts_enabled:
        # Price chart already fetches and summarizes the same market series. Hiding the
        # data-only alternative makes visual requests deterministic instead of letting the
        # model choose get_market_data and then incorrectly claim it cannot show a chart.
        return name != "get_market_data"
    return name not in _CHART_TOOL_NAMES


def build_realtime_tool_schemas(charts_enabled: bool = True) -> list[dict[str, Any]]:
    """Return the OpenAI Realtime tool-declaration list for every registered tool.

    Flat `{"type": "function", "name", "description", "parameters"}` shape — the exact
    form `client.realtime.client_secrets.create`'s `session.tools` expects (verified
    against `openai.types.realtime.RealtimeFunctionToolParam`), NOT the Chat-Completions
    style nested under a `"function"` key.
    """
    return [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_model.model_json_schema(),
        }
        for name, tool in _REALTIME_TOOLS.items()
        if _is_session_tool_enabled(name, charts_enabled=charts_enabled)
    ]


def validate_tool_args(name: str, raw_arguments: dict[str, Any]) -> Any:
    """Look up `name` in the allowlist and validate `raw_arguments` against its schema.

    Raises `ToolNotFoundError` when `name` isn't a registered tool (allowlist gate) and
    `pydantic.ValidationError` when the arguments don't match the tool's schema. Kept
    separate from dispatch so the endpoint can distinguish "unknown tool" from "bad args"
    and map each to the right HTTP status without running any handler.
    """
    tool = _REALTIME_TOOLS.get(name)
    if tool is None:
        raise ToolNotFoundError(name)
    return tool.args_model.model_validate(raw_arguments)


async def dispatch_realtime_tool(
    container: Any, name: str, raw_arguments: dict[str, Any], user_id: str
) -> dict[str, Any]:
    """Validate + dispatch one realtime tool call, returning its JSON-serializable output.

    Security: `name` must be in the allowlist (`ToolNotFoundError` otherwise), arguments
    are validated by the tool's Pydantic model before the handler runs (`ValidationError`
    on bad input), and `user_id` comes from the verified JWT — it is passed to the handler
    positionally and NEVER read from `raw_arguments`.
    """
    typed_args = validate_tool_args(name, raw_arguments)
    tool = _REALTIME_TOOLS[name]
    return await tool.handler(container, typed_args, user_id)


def is_registered_tool(name: str) -> bool:
    """Return whether `name` is in the realtime tool allowlist."""
    return name in _REALTIME_TOOLS
