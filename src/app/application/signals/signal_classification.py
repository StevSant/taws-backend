from pydantic import BaseModel, Field

from app.domain.signals.entities import ImpactClass


class SignalClassification(BaseModel):
    """Structured-output schema the Analyst pipeline asks the chat model to fill in.

    Passed to `model.with_structured_output(SignalClassification)` in
    `generate_signal.py` — mirrors `RouteDecision`'s role for the Supervisor's routing
    node (`infrastructure/agents/route_decision.py`), just for impact classification
    instead of specialist routing.
    """

    impact_class: ImpactClass = Field(
        description="The likely impact of the provided news on the instrument's outlook."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this classification, from 0.0 to 1.0."
    )
    reasoning: str = Field(
        description=(
            "One or two sentences grounding the classification strictly in the provided "
            "news evidence — never facts outside it."
        )
    )
    thesis: str = Field(
        default="",
        description=(
            "A 3-5 sentence analytical thesis: what the evidence implies for the "
            "instrument's outlook and why. Grounded strictly in the provided news, price "
            "context, and historical analogs — never facts outside them."
        ),
    )
    key_drivers: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete factors from the evidence driving this call, each a short phrase."
        ),
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description=(
            "What would invalidate this call — the main risks or counterpoints, each a "
            "short phrase."
        ),
    )
