from typing import Any

from langgraph.types import Send

from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_state import SupervisorState

_CONTRIBUTOR_NODE = "contributor"


def select_specialist_routes(state: SupervisorState) -> str | list[Send]:
    """Keep one route direct; fan multiple routes out as contributor jobs."""
    routes = state.get("routes") or [SupervisorRoute.ADVISOR.value]
    if len(routes) == 1:
        return routes[0]

    shared: dict[str, Any] = {"messages": state["messages"], "routes": routes}
    if locale := state.get("locale"):
        shared["locale"] = locale
    if grounding_context := state.get("grounding_context"):
        shared["grounding_context"] = grounding_context
    return [
        Send(_CONTRIBUTOR_NODE, {**shared, "contributor_route": route}) for route in routes
    ]
