from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.agents.supervisor_route import SupervisorRoute


class RouteDecision(BaseModel):
    """Structured-output schema the supervisor node asks the chat model to fill in.

    Passed to `model.with_structured_output(RouteDecision)` — see
    `supervisor_router_node.py`. Kept intentionally tiny (one enum + a reason string)
    since the model only needs to pick one to three specialists per turn.
    """

    model_config = ConfigDict(ser_json_bytes="utf8")

    routes: list[SupervisorRoute] = Field(
        min_length=1,
        max_length=3,
        description="One to three specialists needed to answer this turn.",
    )
    reason: str = Field(description="One short sentence explaining the routing choice.")

    @model_validator(mode="after")
    def validate_route_combination(self) -> "RouteDecision":
        if len(set(self.routes)) != len(self.routes):
            raise ValueError("routes must be unique")
        scope_routes = {SupervisorRoute.SMALLTALK, SupervisorRoute.OUT_OF_SCOPE}
        if len(self.routes) > 1 and any(route in scope_routes for route in self.routes):
            raise ValueError("scope routes must be selected alone")
        return self
