from pydantic import BaseModel, Field

from app.domain.scenario.entities import ScenarioDirection, ScenarioHorizon, ScenarioMagnitude


class ScenarioSpecExtraction(BaseModel):
    """Structured-output schema the Scenario Lab's free-form Intake step asks the chat
    model to fill in — mirrors `SignalClassification`'s role for the Analyst pipeline
    (`application/signals/signal_classification.py`), just for scenario normalization
    instead of impact classification.

    `affected_symbols` must be chosen only from the tracked-instrument-universe listing
    included in the Intake system prompt (see `NormalizeScenarioIntake`) — the model is
    instructed never to invent a symbol; `resolve_affected_symbols` re-validates this
    afterward regardless, dropping anything that isn't actually in the universe.
    """

    entity: str = Field(
        description=(
            "The core instrument, sector, or theme this scenario is about, e.g. 'NVDA', "
            "'Federal Reserve policy rate', 'global oil supply'."
        )
    )
    event_type: str = Field(
        description=(
            "A short label for the kind of event, e.g. 'earnings_miss', 'macro_rate_shock'."
        )
    )
    magnitude: ScenarioMagnitude = Field(
        description="How large/impactful this event is expected to be."
    )
    horizon: ScenarioHorizon = Field(
        description="The time horizon over which effects are expected to play out."
    )
    title: str = Field(
        description=(
            "A short human-readable title for this scenario, e.g. "
            "'Fed hikes rates by an unexpected 50bp'."
        )
    )
    description: str = Field(
        description=(
            "A one-paragraph normalized restatement of the scenario, grounded strictly in "
            "what the user described — never invent extra facts."
        )
    )
    target_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Explicit target price stated by the user, without a currency symbol. Use null "
            "when the scenario is not about an instrument reaching a price level."
        ),
    )
    direction: ScenarioDirection | None = Field(
        default=None,
        description=(
            "Direction of the primary numeric shock. Use null when no directional move "
            "was stated."
        ),
    )
    timeframe_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description=(
            "Exact timeframe in calendar days when stated or clearly implied; 'tomorrow' "
            "means 1. Use null when only a broad horizon is available."
        ),
    )
    affected_symbols: list[str] = Field(
        default_factory=list,
        description=(
            "Instrument symbols from the tracked universe list above that this scenario "
            "would plausibly affect. Only choose symbols from that exact list — never "
            "invent one."
        ),
    )
