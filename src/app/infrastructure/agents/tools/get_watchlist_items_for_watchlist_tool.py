from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.watchlist.ports import WatchlistRepository


class _GetWatchlistItemsArgs(BaseModel):
    watchlist_id: str = Field(description="The watchlist id to look up tracked instruments for.")


def build_get_watchlist_items_tool(watchlist_repository: WatchlistRepository) -> StructuredTool:
    """Build a LangChain tool resolving which instruments a watchlist tracks.

    Lets the Advisor chain `get_watchlist_items_for_watchlist` -> `get_signals_for_instrument`
    within one bounded tool-calling loop (see `invoke_with_bound_tools.py`) to ground a
    "what does my watchlist look like" question without a briefing already existing.
    """

    async def _run(watchlist_id: str) -> str:
        items = await watchlist_repository.list_items(watchlist_id)
        if not items:
            return f"Watchlist {watchlist_id!r} has no tracked instruments (or doesn't exist)."
        return ", ".join(item.symbol for item in items)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_watchlist_items_for_watchlist",
        description=(
            "List the instrument symbols tracked in one watchlist id. Use this first when "
            "asked about 'my watchlist' with an id, then look up signals for each symbol."
        ),
        args_schema=_GetWatchlistItemsArgs,
    )
