"""`SearchCoins`: thin orchestrator delegating straight to `CoinGeckoSearchProvider`.

No business logic of its own beyond the pass-through — the port already returns
`[]` on zero hits/failure (instrument-search spec).
"""

from app.application.instruments.use_cases import SearchCoins
from app.domain.market.entities import CoinCandidate
from app.domain.market.ports import CoinGeckoSearchProvider

_DOGE = CoinCandidate(id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb="")


class _FakeSearchProvider(CoinGeckoSearchProvider):
    def __init__(self, results: list[CoinCandidate]) -> None:
        self._results = results
        self.received_query: str | None = None

    async def search(self, query: str) -> list[CoinCandidate]:
        self.received_query = query
        return self._results


async def test_execute_delegates_to_the_search_port() -> None:
    provider = _FakeSearchProvider([_DOGE])
    use_case = SearchCoins(search_provider=provider)

    results = await use_case.execute("doge")

    assert results == [_DOGE]
    assert provider.received_query == "doge"


async def test_execute_returns_empty_list_unchanged() -> None:
    provider = _FakeSearchProvider([])
    use_case = SearchCoins(search_provider=provider)

    results = await use_case.execute("zzznonexistentcoin")

    assert results == []
