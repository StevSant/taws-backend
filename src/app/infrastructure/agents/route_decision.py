from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.agents.supervisor_route import SupervisorRoute


class RouteDecision(BaseModel):
    """Structured-output schema the supervisor node asks the chat model to fill in.

    Passed to `model.with_structured_output(RouteDecision)` — see
    `supervisor_router_node.py`. Kept intentionally tiny (one enum + a reason string)
    since the model only needs to pick one specialist per turn.
    """

    model_config = ConfigDict(ser_json_bytes="utf8")

    route: SupervisorRoute = Field(description="The specialist best suited to this turn.")
    reason: str = Field(description="One short sentence explaining the routing choice.")
