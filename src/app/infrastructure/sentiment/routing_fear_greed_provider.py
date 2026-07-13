import logging

from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.errors import FearGreedUnavailableError
from app.domain.sentiment.ports import FearGreedProvider

logger = logging.getLogger(__name__)


class RoutingFearGreedProvider(FearGreedProvider):
    """FearGreedProvider fronting the live alternative.me index. A real reading, or an error.

    Used to fall back to `FixtureFearGreedProvider` on any failure (network error, malformed
    payload, unrecognized classification label). But a Fear & Greed number is a claim about
    how the whole market currently feels, and the UI renders it as a *gauge* — which reads as
    a measurement, not a guess. Serving a fixture there is asserting a market mood that nobody
    measured.
    """

    def __init__(self, live_provider: FearGreedProvider) -> None:
        self._live_provider = live_provider

    async def get_fear_greed_index(self) -> FearGreedReading:
        try:
            return await self._live_provider.get_fear_greed_index()
        except Exception as error:
            logger.warning("Live Fear & Greed index lookup failed.", exc_info=True)
            raise FearGreedUnavailableError(str(error)) from error
