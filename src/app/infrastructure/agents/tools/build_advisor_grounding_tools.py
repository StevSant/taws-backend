from langchain_core.tools import BaseTool

from app.domain.briefing.ports import BriefingRepository
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.agents.tools.get_briefings_for_watchlist_tool import (
    build_get_briefings_for_watchlist_tool,
)
from app.infrastructure.agents.tools.get_signals_for_instrument_tool import (
    build_get_signals_for_instrument_tool,
)
from app.infrastructure.agents.tools.get_watchlist_items_for_watchlist_tool import (
    build_get_watchlist_items_tool,
)


def build_advisor_grounding_tools(
    signal_repository: SignalRepository,
    briefing_repository: BriefingRepository,
    watchlist_repository: WatchlistRepository,
) -> list[BaseTool]:
    """Build the full set of grounding tools, bound only to the `advisor` specialist node.

    See `core/di/container.py`'s `_get_chat_graph` for where these get wired in, and
    `specialist_node_factory.py` for the additive, analyst/quant-unaffected `tools` param.
    """
    return [
        build_get_signals_for_instrument_tool(signal_repository),
        build_get_briefings_for_watchlist_tool(briefing_repository),
        build_get_watchlist_items_tool(watchlist_repository),
    ]
