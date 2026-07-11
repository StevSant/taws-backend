import logging

from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.ports import FearGreedProvider

logger = logging.getLogger(__name__)


class RoutingFearGreedProvider(FearGreedProvider):
    """FearGreedProvider that prefers the live alternative.me adapter and falls back to a
    fixture reading.

    Any exception from the live adapter (network error, malformed payload, unrecognized
    classification label) falls back to `FixtureFearGreedProvider` — same
    "live-preferred, fixture-fallback" shape as `RoutingMacroDataProvider`/
    `RoutingMarketDataProvider`.
    """

    def __init__(
        self, live_provider: FearGreedProvider, fixture_provider: FearGreedProvider
    ) -> None:
        self._live_provider = live_provider
        self._fixture_provider = fixture_provider

    async def get_fear_greed_index(self) -> FearGreedReading:
        try:
            return await self._live_provider.get_fear_greed_index()
        except Exception:
            logger.warning("Live Fear & Greed index lookup failed; using fixture.", exc_info=True)
            return await self._fixture_provider.get_fear_greed_index()
