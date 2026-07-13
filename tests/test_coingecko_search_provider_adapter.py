"""`CoinGeckoSearchProvider` adapter: calls `/search?query=`, maps hits to
`CoinCandidate`, and reuses the same cooldown/circuit-breaker pattern as
`CoinGeckoMarketDataProvider` — a live failure (429/timeout) backs off for
`cooldown_seconds` and serves `[]` instead of hammering CoinGecko on every
subsequent search.
"""

import httpx
import pytest

from app.domain.market.entities import CoinCandidate
from app.infrastructure.marketdata import (
    CoinGeckoCoinSearchProvider as CoinGeckoSearchProviderAdapter,
)

_SEARCH_PAYLOAD = {
    "coins": [
        {
            "id": "dogecoin",
            "symbol": "doge",
            "name": "Dogecoin",
            "market_cap_rank": 10,
            "thumb": "https://assets.coingecko.com/coins/images/5/thumb/dogecoin.png",
        },
        {
            "id": "dogelon-mars",
            "symbol": "elon",
            "name": "Dogelon Mars",
            "market_cap_rank": None,
            "thumb": "https://assets.coingecko.com/coins/images/1/thumb/elon.png",
        },
    ]
}


_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def _build(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(**kwargs)

    return _build


async def test_search_maps_hits_to_coin_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/search"
        assert request.url.params["query"] == "doge"
        return httpx.Response(200, json=_SEARCH_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(base_url="https://api.coingecko.com/api/v3")

    results = await provider.search("doge")

    assert results == [
        CoinCandidate(
            id="dogecoin",
            symbol="doge",
            name="Dogecoin",
            market_cap_rank=10,
            thumb="https://assets.coingecko.com/coins/images/5/thumb/dogecoin.png",
        ),
        CoinCandidate(
            id="dogelon-mars",
            symbol="elon",
            name="Dogelon Mars",
            market_cap_rank=None,
            thumb="https://assets.coingecko.com/coins/images/1/thumb/elon.png",
        ),
    ]


async def test_search_returns_empty_list_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(
        base_url="https://api.coingecko.com/api/v3", cooldown_seconds=60.0
    )

    results = await provider.search("doge")

    assert results == []


async def test_search_returns_empty_list_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(base_url="https://api.coingecko.com/api/v3")

    results = await provider.search("doge")

    assert results == []


async def test_search_serves_empty_list_while_in_cooldown_without_a_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(
        base_url="https://api.coingecko.com/api/v3", cooldown_seconds=60.0
    )

    await provider.search("doge")  # enters cooldown after the 429
    results = await provider.search("doge")  # should short-circuit, no live call

    assert results == []
    assert call_count == 1


async def test_search_returns_empty_list_on_malformed_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEDIUM fix (post-hoc adversarial review): a 200 response with a body that
    is not valid JSON must fail soft (`[]`), not raise `json.JSONDecodeError` and
    500 the `GET /instruments/search` endpoint."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not json at all", headers={"content-type": "text/plain"}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(base_url="https://api.coingecko.com/api/v3")

    results = await provider.search("doge")

    assert results == []


async def test_search_returns_empty_list_when_hits_are_missing_required_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 200 response with valid JSON but a shape CoinGecko never actually sends
    (missing `id`/`symbol`/`name`) must also fail soft instead of raising `KeyError`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"coins": [{"unexpected": "shape"}]})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoSearchProviderAdapter(base_url="https://api.coingecko.com/api/v3")

    results = await provider.search("doge")

    assert results == []
