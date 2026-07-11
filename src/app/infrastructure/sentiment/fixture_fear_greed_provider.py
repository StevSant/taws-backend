from datetime import UTC, datetime

from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.ports import FearGreedProvider
from app.infrastructure.sentiment.parse_fear_greed_classification import (
    parse_fear_greed_classification,
)


class FixtureFearGreedProvider(FearGreedProvider):
    """FearGreedProvider fallback: a static, plausible Fear & Greed reading from `Settings`.

    Used by `RoutingFearGreedProvider` whenever alternative.me is unreachable or returns an
    unparseable payload, so Sentiment Analyst readings stay available in dev without network
    access — consistent with `FixtureMacroDataProvider`/`FixtureNewsProvider`.
    """

    def __init__(self, fixture_value: int, fixture_classification: str) -> None:
        self._fixture_value = fixture_value
        self._fixture_classification = parse_fear_greed_classification(fixture_classification)

    async def get_fear_greed_index(self) -> FearGreedReading:
        return FearGreedReading(
            value=self._fixture_value,
            classification=self._fixture_classification,
            as_of=datetime.now(UTC),
        )
