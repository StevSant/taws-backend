from abc import ABC, abstractmethod

from app.domain.market.entities import CoinCandidate


class CoinGeckoSearchProvider(ABC):
    """Port for resolving arbitrary crypto name/ticker queries against CoinGecko.

    Adapter: `infrastructure/marketdata/coingecko_search_provider.py` (`/search`
    endpoint), reusing the cooldown/circuit-breaker pattern from
    `CoinGeckoMarketDataProvider`. Consumed by the `SearchCoins` use case.
    """

    @abstractmethod
    async def search(self, query: str) -> list[CoinCandidate]:
        """Return ranked candidates for `query`; empty list on no hits or failure."""
        raise NotImplementedError
