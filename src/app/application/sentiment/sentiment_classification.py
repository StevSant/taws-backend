from pydantic import BaseModel, Field


class SentimentClassification(BaseModel):
    """Structured-output schema the Sentiment Analyst asks the chat model to fill in.

    Passed to `LLMProvider.complete_structured(...)` in `analyze_sentiment.py` — mirrors
    `SignalClassification`'s role for the Analyst pipeline
    (`application/signals/signal_classification.py`), just for a continuous tone score
    instead of a four-way impact classification. Deliberately does NOT include a
    categorical label: `AnalyzeSentiment` deterministically buckets `tone_score` into
    `SentimentLabel` afterward (see that use case's `_bucket_tone_label`), so the model
    only ever has to produce one number it can ground in the provided evidence.
    """

    tone_score: float = Field(
        ge=-1.0,
        le=1.0,
        description=(
            "Overall news tone for the instrument, from -1.0 (very negative) to 1.0 "
            "(very positive). Use a value near 0.0 when there is no meaningful news or "
            "coverage is too mixed/inconclusive to call a direction."
        ),
    )
    reasoning: str = Field(
        description=(
            "One or two sentences grounding the tone score strictly in the provided "
            "news evidence — never facts outside it."
        )
    )
