from app.domain.market.entities import CoinCandidate
from app.domain.market.ports import CoinGeckoSearchProvider


class SearchCoins:
    """Thin orchestrator over `CoinGeckoSearchProvider` for `GET /instruments/search`.

    No business logic beyond delegation — the port's own contract already
    returns `[]` on zero hits or a soft CoinGecko failure (instrument-search
    spec's "no hits returns an empty list" / "unavailability fails soft").
    """

    def __init__(self, search_provider: CoinGeckoSearchProvider) -> None:
        self._search_provider = search_provider

    async def execute(self, query: str) -> list[CoinCandidate]:
        return await self._search_provider.search(query)
