from pydantic import BaseModel, Field


class InstrumentNarrative(BaseModel):
    """One instrument's short narrative inside a `BriefingComposition` response."""

    symbol: str = Field(description="The instrument symbol this narrative covers.")
    narrative: str = Field(
        description=(
            "One or two sentences summarizing this instrument's signals — impact "
            "direction, confidence, and notable evidence. Ground every claim strictly in "
            "the provided signals for this instrument; never invent facts."
        )
    )


class BriefingComposition(BaseModel):
    """Structured-output schema the Advisor pipeline asks the chat model to fill in
    (issue #16's fuller briefing document structure).

    Mirrors `SignalClassification`'s role for the Analyst pipeline
    (`application/signals/signal_classification.py`): passed to
    `LLMProvider.complete_structured(...)` in `generate_briefing.py` so one LLM call
    produces both the document's executive summary and its per-instrument narratives,
    instead of a second LLM round-trip per instrument.
    """

    executive_summary: str = Field(
        description=(
            "A short (2-4 sentence) plain-language overview of what the provided signals "
            "show across the whole watchlist. Never recommend trades, promise returns, or "
            "give buy/sell/execution instructions — surface research and alert-worthy "
            "points only."
        )
    )
    instrument_narratives: list[InstrumentNarrative] = Field(
        default_factory=list,
        description=(
            "One narrative per instrument that has signals in the provided data. Do not "
            "include an entry for an instrument with no signals provided."
        ),
    )
