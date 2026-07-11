from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.sentiment.entities.fear_greed_reading import FearGreedReading
from app.domain.sentiment.entities.sentiment_label import SentimentLabel
from app.domain.signals.entities import SignalEvidence


@dataclass(slots=True)
class SentimentReading:
    """The Sentiment Analyst's produced output for one instrument (issue #21).

    Written by the Sentiment Analyst. `tone_score` is on the same `-1.0..1.0` scale as
    `domain/market/entities/news_item.py`'s `NewsItem.sentiment_score` (negative ->
    negative tone), chosen for consistency rather than inventing a second sentiment
    scale in the codebase; `tone_label` is `tone_score` deterministically bucketed into
    `SentimentLabel`. `fear_greed` is alternative.me's market-wide index reading,
    attached as context for this instrument's read (see `FearGreedReading`'s docstring
    for why it isn't itself per-instrument). `evidence` reuses `domain/signals`'
    `SignalEvidence` (source + date, optionally a URL/detail) — same "cite dated,
    sourced news" shape the Analyst pipeline already uses, rather than inventing a
    parallel evidence type. No trading/execution fields exist; `disclaimer` is the same
    product invariant every other specialist output carries.
    """

    id: str
    instrument_symbol: str
    tone_score: float
    tone_label: SentimentLabel
    fear_greed: FearGreedReading
    evidence: list[SignalEvidence]
    rationale: str
    disclaimer: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
