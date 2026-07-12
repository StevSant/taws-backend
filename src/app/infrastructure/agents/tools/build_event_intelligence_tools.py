from langchain_core.tools import BaseTool

from app.domain.event_intelligence.ports import EventRepositoryPort
from app.infrastructure.agents.tools.get_recent_events_tool import (
    build_get_recent_events_tool,
)


def build_event_intelligence_tools(
    event_repository: EventRepositoryPort,
) -> list[BaseTool]:
    """Build tools that expose the Event Intelligence pipeline to the advisor.

    Currently provides a single tool: `get_recent_events` — retrieves the most
    recent analyzed news events with importance scores, affected sectors/assets,
    and suggested follow-up questions.
    """
    return [build_get_recent_events_tool(event_repository)]
