import asyncio

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.application.quant import MarketStats
from app.application.quant.use_cases import ComputeMarketStats
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.agents.tools.resolve_tool_user_id import resolve_tool_user_id

# Short stats window so "how are my assets doing?" reads as "today", mirroring
# `get_market_movers_tool`'s default: yesterday's close is the baseline.
_STATS_WINDOW_DAYS = 2


class _GetWatchlistArgs(BaseModel):
    """No arguments: the acting user comes from the injected config, never from the model."""


def build_get_watchlist_tool(
    watchlist_repository: WatchlistRepository, compute_market_stats: ComputeMarketStats
) -> StructuredTool:
    """Build the tool exposing the caller's OWN watchlists (with a price snapshot) to chat.

    The text-chat sibling of the realtime `get_watchlist` handler
    (`infrastructure/realtime/tools/handlers/get_watchlist_handler.py`). SECURITY: the
    acting user id comes from the turn's `RunnableConfig` (`resolve_tool_user_id`), where
    `LangGraphAgentRunner.stream` put the verified JWT's id — it is NEVER a model-supplied
    argument, so a chat turn can only ever read the authenticated user's own watchlists.
    This is the ownership pattern that unblocks per-user grounding tools; the earlier
    removal (see `build_advisor_grounding_tools`) predates chat requiring auth.

    Unlike the voice handler (names + symbols only, narrated), each symbol also gets a
    small `ComputeMarketStats` snapshot so one tool call answers "how are my assets
    doing?" without a follow-up round-trip per instrument. A per-symbol stats failure
    degrades to "price data unavailable" for that row only.
    """

    async def _run(config: RunnableConfig) -> str:
        user_id = resolve_tool_user_id(config)
        if user_id is None:
            return (
                "No authenticated user is attached to this conversation, so watchlists "
                "cannot be read. Tell the user to sign in and retry."
            )

        watchlists = await watchlist_repository.list_for_user(user_id)
        if not watchlists:
            return (
                "The user has no watchlists yet. Suggest adding instruments from the "
                "Briefings/Informes page to get personalized tracking."
            )

        lines = [f"The user's watchlists ({len(watchlists)}):"]
        for watchlist in watchlists:
            items = await watchlist_repository.list_items(watchlist.id)
            if not items:
                lines.append(f'- "{watchlist.name}": empty')
                continue
            lines.append(f'- "{watchlist.name}" ({len(items)} instruments):')
            stats_by_symbol = await _stats_for(compute_market_stats, [i.symbol for i in items])
            lines.extend(
                _format_item(item.symbol, stats_by_symbol.get(item.symbol)) for item in items
            )
        return "\n".join(lines)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_watchlist",
        description=(
            "Read the user's OWN watchlists: each list's name, its tracked instrument "
            "symbols, and a fresh price snapshot per symbol. Always call this before "
            "answering anything about 'my assets', 'my watchlist', 'my portfolio', or "
            "giving advice personalized to what the user tracks."
        ),
        args_schema=_GetWatchlistArgs,
    )


async def _stats_for(
    compute_market_stats: ComputeMarketStats, symbols: list[str]
) -> dict[str, MarketStats]:
    """Fetch a bounded concurrent stats snapshot; a failed symbol is simply absent."""

    async def _one(symbol: str) -> tuple[str, MarketStats | None]:
        try:
            return symbol, await compute_market_stats.execute(symbol, _STATS_WINDOW_DAYS)
        except Exception:  # noqa: BLE001 — one dark symbol must not blank the whole list
            return symbol, None

    results = await asyncio.gather(*(_one(symbol) for symbol in dict.fromkeys(symbols)))
    return {symbol: stats for symbol, stats in results if stats is not None}


def _format_item(symbol: str, stats: MarketStats | None) -> str:
    if stats is None or stats.last_price is None:
        return f"  - {symbol}: price data unavailable right now (do not estimate it)"
    delta = (
        f"{stats.price_delta_pct:+.2f}% over the last {_STATS_WINDOW_DAYS} day(s)"
        if stats.price_delta_pct is not None
        else "change unavailable"
    )
    return f"  - {symbol}: last price {stats.last_price:.4f}, {delta}"
