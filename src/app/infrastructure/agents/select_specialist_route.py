from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.supervisor_state import SupervisorState


def select_specialist_route(state: SupervisorState) -> str:
    """Conditional-edge selector: read the route the supervisor node just chose.

    Falls back to `SupervisorRoute.ADVISOR` if `route` is somehow missing, so a
    malformed state never leaves the graph without a specialist edge to follow.
    """
    return state.get("route", SupervisorRoute.ADVISOR.value)
