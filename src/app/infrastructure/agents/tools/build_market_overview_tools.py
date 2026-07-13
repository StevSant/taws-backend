from langchain_core.tools import BaseTool

from app.application.instruments.use_cases import ListEnrichedInstruments
from app.infrastructure.agents.tools.get_market_movers_tool import build_get_market_movers_tool


def build_market_overview_tools(
    list_enriched_instruments: ListEnrichedInstruments, default_locale: str
) -> list[BaseTool]:
    """Build the market-overview (whole-universe) tools shared by `advisor` and `analyst`.

    Everything here ranks or summarizes the FULL curated universe rather than one symbol —
    starting with `get_market_movers` (top gainers/losers/most volatile/trending). Safe for
    the chat route for the same reason `build_quant_grounding_tools` documents: it reads
    public market data and market-wide cached signals, never per-user persisted data.

    Bound to BOTH the `advisor` (the router's catch-all, where "what moved today?" usually
    lands) and the `analyst` (where "analyze today's market" lands) — see
    `Container._get_chat_graph`.

    `default_locale` is only the fallback — the tool prefers the turn's locale from its
    injected `RunnableConfig` (see `resolve_tool_locale`).
    """
    return [build_get_market_movers_tool(list_enriched_instruments, default_locale)]
