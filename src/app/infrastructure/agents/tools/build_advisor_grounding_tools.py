from langchain_core.tools import BaseTool

from app.domain.signals.ports import SignalRepository
from app.infrastructure.agents.tools.get_signals_for_instrument_tool import (
    build_get_signals_for_instrument_tool,
)


def build_advisor_grounding_tools(signal_repository: SignalRepository) -> list[BaseTool]:
    """Build the grounding tools bound only to the `advisor` specialist node.

    Deliberately signal-only: `POST /api/v1/chat/stream` (`api/v1/routers/chat.py`) has
    no authentication at all — no `require_current_user`, no `user_id` anywhere in
    `ChatRequest` — so any tool that resolves a raw `watchlist_id` string extracted from
    chat text into a `WatchlistRepository`/`BriefingRepository` lookup without an
    ownership check would leak another user's private data to an anonymous caller.
    `Signal`s aren't per-user (same visibility as `GET /api/v1/news`), so they're the
    only persisted data this route can safely ground answers in today.

    Watchlist/briefing grounding tools existed in an earlier version of this file and
    were removed for exactly this reason (caught in review) — reintroducing them
    requires a real chat-auth issue that threads `user_id` through `ChatRequest` ->
    `StreamReply` -> graph state first, with an ownership check inside the tool itself
    (not just trusting whatever id string the LLM extracted from the message). See the
    Engram note under `architecture/analyst-advisor-pipeline` for the full writeup.

    See `core/di/container.py`'s `_get_chat_graph` for where this gets wired in, and
    `specialist_node_factory.py` for the additive, analyst/quant-unaffected `tools` param.
    """
    return [build_get_signals_for_instrument_tool(signal_repository)]
