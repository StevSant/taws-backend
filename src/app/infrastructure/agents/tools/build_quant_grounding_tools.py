from langchain_core.tools import BaseTool

from app.application.quant.use_cases.compute_event_study import ComputeEventStudy
from app.application.quant.use_cases.compute_market_stats import ComputeMarketStats
from app.infrastructure.agents.tools.get_event_study_stats_tool import (
    build_get_event_study_stats_tool,
)
from app.infrastructure.agents.tools.get_market_stats_tool import build_get_market_stats_tool


def build_quant_grounding_tools(
    compute_market_stats: ComputeMarketStats, compute_event_study: ComputeEventStudy
) -> list[BaseTool]:
    """Build the grounding tools bound only to the `quant` specialist node.

    Unlike `build_advisor_grounding_tools` (deliberately signal-only because chat has no
    auth — see that file's docstring), these tools are safe for the unauthenticated
    `POST /api/v1/chat/stream` route: `MarketStats`/`EventStudyStats` are computed
    on-demand from `MarketDataProvider`, not per-user persisted data — same public
    visibility as `GET /api/v1/news` / `GET /api/v1/instruments` / the Analyst's
    `Signal`s.

    See `core/di/container.py`'s `_get_chat_graph` for where this gets wired in, and
    `specialist_node_factory.py` for the additive, analyst/advisor-unaffected `tools`
    param.
    """
    return [
        build_get_market_stats_tool(compute_market_stats),
        build_get_event_study_stats_tool(compute_event_study),
    ]
