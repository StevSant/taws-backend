from langchain_core.tools import BaseTool

from app.domain.market.ports import NewsProvider
from app.domain.signals.ports import SignalRepository
from app.infrastructure.agents.tools.get_news_tool import build_get_news_tool
from app.infrastructure.agents.tools.get_signals_for_instrument_tool import (
    build_get_signals_for_instrument_tool,
)


def build_advisor_grounding_tools(
    signal_repository: SignalRepository,
    news_provider: NewsProvider,
) -> list[BaseTool]:
    """Build the grounding tools bound to the `advisor` (catch-all) specialist node.

    The advisor is the router's catch-all ("every other genuine markets question"), so a
    news-flavoured question — "latest big-tech news", "what's happening in markets" — often
    lands here rather than on the analyst. Without a news tool the advisor could only refuse
    ("I have no live headlines"), even though real, sourced news was one lookup away — the
    honest-but-unhelpful reply the user actually saw. `get_news` closes that gap so a
    misrouted news question still grounds on real headlines instead of dead-ending.

    Adding `get_news` here is safe on the unauthenticated `POST /api/v1/chat/stream` route:
    news is market-wide, not per-user (same visibility as `GET /api/v1/news`), so it carries
    none of the cross-tenant-leak risk that kept watchlist/briefing grounding tools out.
    That is the same "public, non-per-user data" test `Signal`s and the Scenario tool already
    pass — see below.

    Still deliberately signal-only for *persisted user data*: any tool resolving a raw
    `watchlist_id`/`briefing_id` from chat text into a repository lookup without an ownership
    check would leak another user's private data. Those tools existed in an earlier version
    and were removed for exactly that reason (caught in review) — at the time chat had no
    auth at all. That precondition has since landed: `/chat/stream` requires a verified user
    and `LangGraphAgentRunner.stream` publishes the JWT's `user_id` in the run config, which
    is the ONLY sanctioned channel for per-user tools — see `resolve_tool_user_id` and
    `get_watchlist_tool` (wired in `Container._get_chat_graph`, not in this builder) for the
    pattern; model-supplied id arguments remain forbidden. See the Engram note under
    `architecture/analyst-advisor-pipeline`.

    See `core/di/container.py`'s `_get_chat_graph` for where this gets wired in, and
    `specialist_node_factory.py` for the additive, analyst/quant-unaffected `tools` param.
    """
    return [
        build_get_signals_for_instrument_tool(signal_repository),
        build_get_news_tool(news_provider),
    ]
