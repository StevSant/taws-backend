from dataclasses import dataclass
from datetime import datetime

from app.domain.sentiment.entities.fear_greed_classification import FearGreedClassification


@dataclass(frozen=True, slots=True)
class FearGreedReading:
    """A single Fear & Greed Index reading (alternative.me's Crypto Fear & Greed Index).

    Market-wide, not per-instrument — alternative.me publishes one index value for the
    whole crypto market, not a separate reading per asset. `AnalyzeSentiment` attaches
    this same reading as context alongside each instrument's news-tone score (see that
    use case's docstring for the "per asset" framing this implies).
    """

    value: int
    classification: FearGreedClassification
    as_of: datetime
