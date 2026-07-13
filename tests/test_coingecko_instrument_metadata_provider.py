"""Track Instruments Catalog Slice 3 (enrichment): `CoinGeckoInstrumentMetadataProvider`.

- ONE batch `/coins/markets?ids=` call for N symbols (never one call per symbol).
- Missing/failed symbols are simply omitted from the returned dict — the caller
  maps that absence onto `null` fields.
- CoinGecko fully down -> returns `{}` (empty dict), no exception.
- Reuses the shared cooldown/circuit-breaker pattern from `CoinGeckoMarketDataProvider`.
"""

import httpx
import pytest

from app.domain.market.entities import InstrumentMetadata
from app.infrastructure.marketdata import CoinGeckoInstrumentMetadataProvider

_MARKETS_PAYLOAD = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "market_cap": 1_200_000_000_000.0,
        "total_volume": 45_000_000_000.0,
        "price_change_percentage_7d_in_currency": 5.5,
    },
    {
        "id": "ethereum",
        "symbol": "eth",
        "market_cap": 400_000_000_000.0,
        "total_volume": 20_000_000_000.0,
        "price_change_percentage_7d_in_currency": -2.1,
    },
]

_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def _build(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(**kwargs)

    return _build


async def test_get_metadata_batch_makes_one_call_for_all_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        assert request.url.path == "/api/v3/coins/markets"
        assert request.url.params["ids"] == "bitcoin,ethereum"
        assert request.url.params["price_change_percentage"] == "7d"
        return httpx.Response(200, json=_MARKETS_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin", "ETH": "ethereum"},
    )

    result = await provider.get_metadata_batch(["BTC", "ETH"])

    assert call_count == 1
    assert result == {
        "BTC": InstrumentMetadata(
            market_cap=1_200_000_000_000.0, volume_24h=45_000_000_000.0, change_7d_pct=5.5
        ),
        "ETH": InstrumentMetadata(
            market_cap=400_000_000_000.0, volume_24h=20_000_000_000.0, change_7d_pct=-2.1
        ),
    }


async def test_symbols_without_a_coingecko_id_override_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stock symbol (no `coingecko_id_overrides` entry) never reaches CoinGecko
    and is simply absent from the result — the caller maps that to `null`."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["ids"] == "bitcoin"
        return httpx.Response(200, json=[_MARKETS_PAYLOAD[0]])

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin"},
    )

    result = await provider.get_metadata_batch(["BTC", "AAPL"])

    assert set(result.keys()) == {"BTC"}


async def test_no_symbols_resolve_to_a_coingecko_id_returns_empty_dict_without_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=[])

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3", coingecko_id_overrides={}
    )

    result = await provider.get_metadata_batch(["AAPL", "MSFT"])

    assert result == {}
    assert call_count == 0


async def test_coingecko_hits_missing_from_the_response_are_simply_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CoinGecko may not return a row for every requested id (e.g. delisted coin) —
    the missing symbol is simply absent from the result, not an error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_MARKETS_PAYLOAD[0]])  # only bitcoin, no ethereum

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin", "ETH": "ethereum"},
    )

    result = await provider.get_metadata_batch(["BTC", "ETH"])

    assert set(result.keys()) == {"BTC"}


async def test_rate_limited_response_returns_empty_dict_no_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin"},
        cooldown_seconds=60.0,
    )

    result = await provider.get_metadata_batch(["BTC"])

    assert result == {}


async def test_fully_down_serves_empty_dict_while_in_cooldown_without_a_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin"},
        cooldown_seconds=60.0,
    )

    await provider.get_metadata_batch(["BTC"])  # enters cooldown after the 429
    result = await provider.get_metadata_batch(["BTC"])  # short-circuit, no live call

    assert result == {}
    assert call_count == 1


async def test_malformed_response_body_returns_empty_dict_no_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not json at all", headers={"content-type": "text/plain"}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides={"BTC": "bitcoin"},
    )

    result = await provider.get_metadata_batch(["BTC"])

    assert result == {}
