"""`CoinGeckoSearchProvider` ABC: `async search(query) -> list[CoinCandidate]`.

A minimal fake implementation must satisfy the contract — proves the port shape
before any real HTTP adapter exists.
"""

from app.domain.market.entities import CoinCandidate
from app.domain.market.ports import CoinGeckoSearchProvider


class _FakeSearchProvider(CoinGeckoSearchProvider):
    async def search(self, query: str) -> list[CoinCandidate]:
        return [
            CoinCandidate(
                id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb=""
            )
        ]


async def test_fake_search_provider_satisfies_the_port() -> None:
    provider: CoinGeckoSearchProvider = _FakeSearchProvider()

    results = await provider.search("doge")

    assert results == [
        CoinCandidate(id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb="")
    ]
