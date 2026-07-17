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

    `is_market_relevant` is a scope gate decided FIRST (it's the first field so the model
    commits to it before normalizing the rest): the Scenario Lab analyzes market/economic/
    financial "what ifs", not personal, relationship, sports, or entertainment ones. When it
    is false, `NormalizeScenarioIntake` refuses the run with `rejection_reason` rather than
    fabricating a market analysis of an off-topic prompt.
    """

    is_market_relevant: bool = Field(
        description=(
            "True only if this describes a MARKET, ECONOMIC, or FINANCIAL scenario — an "
            "event about instruments, sectors, macro conditions, commodities, rates, "
            "companies, or policy that could plausibly move markets. False for anything with "
            "no market dimension (personal life, relationships, sports, entertainment, etc.)."
        )
    )
    rejection_reason: str = Field(
        default="",
        description=(
            "When is_market_relevant is false: one short, polite sentence, WRITTEN IN THE "
            "USER'S LANGUAGE, telling them the Scenario Lab only analyzes market and economic "
            "scenarios. Empty string when is_market_relevant is true."
        ),
    )
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
            "Direction of the primary numeric shock. Use null when no directional move was stated."
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
