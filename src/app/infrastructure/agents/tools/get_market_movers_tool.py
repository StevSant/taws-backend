from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.application.instruments import EnrichedInstrument, InstrumentHighlights
from app.application.instruments.use_cases import ListEnrichedInstruments
from app.domain.market.entities import AssetClass
from app.infrastructure.agents.tools.resolve_tool_locale import resolve_tool_locale

# "Today's movers" needs yesterday's close as the baseline, so the shortest meaningful
# window is 2 calendar days — same lower bound `GET /instruments/enriched` enforces.
_DEFAULT_WINDOW_DAYS = 2
_MAX_WINDOW_DAYS = 365


class _GetMarketMoversArgs(BaseModel):
    window_days: int = Field(
        default=_DEFAULT_WINDOW_DAYS,
        description=(
            "How many days of price history the ranking covers. Use the default (2) for "
            "'today's movers'; use 7 or 30 for weekly/monthly movers."
        ),
        ge=2,
        le=_MAX_WINDOW_DAYS,
    )
    asset_class: AssetClass | None = Field(
        default=None,
        description=(
            "Optionally restrict the ranking to one asset class "
            "(stock, crypto, credit, commodity, forex). Omit to rank everything."
        ),
    )


def build_get_market_movers_tool(
    list_enriched_instruments: ListEnrichedInstruments, default_locale: str
) -> StructuredTool:
    """Build a LangChain tool ranking the tracked universe's top movers.

    Thin wrapper over `ListEnrichedInstruments` — the SAME use case that powers
    `GET /api/v1/instruments/enriched` and its explorer leaderboards — so the chat agent
    and the markets page can never disagree about who today's gainers/losers are. Before
    this tool existed the agent had only per-symbol tools, so a "top movers today"
    question was honestly (but unhelpfully) refused.

    The locale comes from the turn's `RunnableConfig` (see `resolve_tool_locale`) because
    the trending leaderboard is built from cached signals, which are stored per
    `(symbol, locale)`.
    """

    async def _run(
        config: RunnableConfig,
        window_days: int = _DEFAULT_WINDOW_DAYS,
        asset_class: AssetClass | None = None,
    ) -> str:
        page = await list_enriched_instruments.execute(
            locale=resolve_tool_locale(config, default_locale),
            asset_class=asset_class,
            page=1,
            page_size=1,
            window_days=window_days,
        )
        return _format_highlights(page.highlights, window_days, asset_class)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_market_movers",
        description=(
            "Rank the tracked instrument universe's top movers over a window of days: top "
            "gainers, top losers, most volatile, and trending (freshest AI signals). Use "
            "this for any 'what moved today', 'top movers', 'biggest gainers/losers', or "
            "market-overview question — never invent a ranking or answer one from memory."
        ),
        args_schema=_GetMarketMoversArgs,
    )


def _format_highlights(
    highlights: InstrumentHighlights, window_days: int, asset_class: AssetClass | None
) -> str:
    scope = f"tracked {asset_class.value} instruments" if asset_class else "the tracked universe"
    has_price_data = bool(
        highlights.top_gainers or highlights.top_losers or highlights.most_volatile
    )
    if not has_price_data:
        return (
            f"Market movers are UNAVAILABLE for {scope} right now — the upstream price "
            f"provider returned no usable data. Tell the user the ranking is unavailable "
            f"and suggest they retry shortly. Do NOT invent a ranking or estimate one "
            f"from memory."
        )

    lines = [f"Top movers across {scope}, computed over the last {window_days} day(s):"]
    lines.extend(_section("Top gainers", highlights.top_gainers))
    lines.extend(_section("Top losers", highlights.top_losers))
    lines.extend(_volatility_section(highlights.most_volatile))
    lines.extend(_trending_section(highlights.trending))
    lines.append("Rankings only cover the curated instrument universe, not the whole market.")
    return "\n".join(lines)


def _section(title: str, items: list[EnrichedInstrument]) -> list[str]:
    if not items:
        return [f"- {title}: none in this window"]
    lines = [f"- {title}:"]
    lines.extend(
        f"  - {item.symbol} ({item.name}): {item.price_delta_pct:+.2f}%{_last_price_suffix(item)}"
        for item in items
        if item.price_delta_pct is not None
    )
    return lines


def _volatility_section(items: list[EnrichedInstrument]) -> list[str]:
    if not items:
        return ["- Most volatile: none in this window"]
    lines = ["- Most volatile (annualized):"]
    lines.extend(
        f"  - {item.symbol} ({item.name}): {item.volatility_pct:.2f}%"
        for item in items
        if item.volatility_pct is not None
    )
    return lines


def _trending_section(items: list[EnrichedInstrument]) -> list[str]:
    if not items:
        return ["- Trending (freshest AI signals): none available"]
    lines = ["- Trending (freshest AI signals):"]
    lines.extend(
        f"  - {item.symbol} ({item.name}): signal from "
        f"{item.latest_signal.created_at.date().isoformat()}"
        for item in items
        if item.latest_signal is not None
    )
    return lines


def _last_price_suffix(item: EnrichedInstrument) -> str:
    if item.last_price is None:
        return ""
    return f", last price {item.last_price:.4f} {item.currency}"
