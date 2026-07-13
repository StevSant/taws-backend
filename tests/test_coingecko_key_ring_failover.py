"""CoinGecko API-key failover: a 429 on one key must NOT blank out crypto.

Regression cover for the production `503 No real market data available for BTC`: the
single Demo key ran out of quota, its 429 armed the provider-wide 300s circuit breaker,
and every crypto instrument went dark for 5 minutes. With a key ring, a 429 benches only
the throttled key and the same request is retried on the next one.
"""

import httpx
import pytest

from app.core.config import Settings
from app.domain.market.entities import AssetClass, Instrument
from app.infrastructure.marketdata import (
    CoinGeckoInstrumentMetadataProvider,
    CoinGeckoKeyRing,
    CoinGeckoMarketDataProvider,
)

_BTC = Instrument(symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")
_OVERRIDES = {"BTC": "bitcoin"}
_API_KEY_HEADER = "x-cg-demo-api-key"

_MARKET_CHART_PAYLOAD = {"prices": [[1_700_000_000_000, 42_000.0], [1_700_086_400_000, 43_000.0]]}
_MARKETS_PAYLOAD = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "market_cap": 1_200_000_000_000.0,
        "total_volume": 45_000_000_000.0,
        "price_change_percentage_7d_in_currency": 5.5,
    }
]

_RealAsyncClient = httpx.AsyncClient


def _client_factory(handler):
    def _build(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _RealAsyncClient(**kwargs)

    return _build


def _build_provider(key_ring: CoinGeckoKeyRing) -> CoinGeckoMarketDataProvider:
    """A price provider with caching OFF, so each call actually hits the transport."""
    return CoinGeckoMarketDataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides=_OVERRIDES,
        cache_ttl_seconds=0.0,
        key_ring=key_ring,
    )


async def test_rate_limited_key_fails_over_to_the_fallback_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers[_API_KEY_HEADER]
        keys_seen.append(key)
        if key == "CG-primary":
            return httpx.Response(429, json={"status": {"error_code": 429}})
        return httpx.Response(200, json=_MARKET_CHART_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = _build_provider(CoinGeckoKeyRing(["CG-primary", "CG-fallback"]))

    series = await provider.get_price_series(_BTC, days=30)

    # The 429 on the primary was retried on the fallback IN THE SAME CALL — the caller
    # gets real candles, not the empty series that becomes a 503.
    assert keys_seen == ["CG-primary", "CG-fallback"]
    assert [candle.close for candle in series.candles] == [42_000.0, 43_000.0]


async def test_benched_key_is_skipped_on_the_next_call(monkeypatch: pytest.MonkeyPatch) -> None:
    keys_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers[_API_KEY_HEADER]
        keys_seen.append(key)
        if key == "CG-primary":
            return httpx.Response(429, json={})
        return httpx.Response(200, json=_MARKET_CHART_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = _build_provider(CoinGeckoKeyRing(["CG-primary", "CG-fallback"]))

    await provider.get_price_series(_BTC, days=30)
    keys_seen.clear()
    series = await provider.get_price_series(_BTC, days=30)

    # The throttled key stays benched, so the second call does NOT pay a wasted round trip
    # to re-learn it is rate-limited — it goes straight to the fallback.
    assert keys_seen == ["CG-fallback"]
    assert len(series.candles) == 2


async def test_all_keys_rate_limited_does_not_arm_the_provider_wide_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limited = True

    def handler(request: httpx.Request) -> httpx.Response:
        if rate_limited:
            return httpx.Response(429, json={})
        return httpx.Response(200, json=_MARKET_CHART_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    # Zero bench window: the keys are "recovered" by the time the second call runs, which is
    # what a rolled-over per-minute window looks like.
    key_ring = CoinGeckoKeyRing(["CG-primary", "CG-fallback"], key_cooldown_seconds=0.0)
    provider = _build_provider(key_ring)

    assert (await provider.get_price_series(_BTC, days=30)).candles == []

    rate_limited = False
    series = await provider.get_price_series(_BTC, days=30)

    # THE REGRESSION: a 429 used to arm the 300s provider-wide breaker, so even once the keys
    # recovered every crypto instrument stayed dark (503) for the rest of the window. It must
    # recover as soon as a key does.
    assert [candle.close for candle in series.candles] == [42_000.0, 43_000.0]


async def test_one_ring_shares_rate_limit_state_across_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers[_API_KEY_HEADER]
        keys_seen.append(key)
        if key == "CG-primary":
            return httpx.Response(429, json={})
        if request.url.path.endswith("/coins/markets"):
            return httpx.Response(200, json=_MARKETS_PAYLOAD)
        return httpx.Response(200, json=_MARKET_CHART_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    key_ring = CoinGeckoKeyRing(["CG-primary", "CG-fallback"])
    prices = _build_provider(key_ring)
    metadata = CoinGeckoInstrumentMetadataProvider(
        base_url="https://api.coingecko.com/api/v3",
        coingecko_id_overrides=_OVERRIDES,
        key_ring=key_ring,
    )

    await prices.get_price_series(_BTC, days=30)  # burns the primary key's quota
    keys_seen.clear()
    result = await metadata.get_metadata_batch(["BTC"])

    # All three CoinGecko adapters spend the SAME per-key quota, so the metadata adapter must
    # inherit the price adapter's discovery that the primary key is exhausted.
    assert keys_seen == ["CG-fallback"]
    assert result["BTC"].market_cap == 1_200_000_000_000.0


async def test_keyless_ring_sends_no_api_key_header(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert _API_KEY_HEADER not in request.headers
        return httpx.Response(200, json=_MARKET_CHART_PAYLOAD)

    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(handler))
    provider = _build_provider(CoinGeckoKeyRing([]))

    assert len((await provider.get_price_series(_BTC, days=30)).candles) == 2


def test_settings_parses_a_comma_separated_key_list() -> None:
    assert Settings(coingecko_api_key="CG-aaa, CG-bbb ,").coingecko_api_keys == [
        "CG-aaa",
        "CG-bbb",
    ]
    # A single key (the shape every existing deployment already has) is untouched.
    assert Settings(coingecko_api_key="CG-aaa").coingecko_api_keys == ["CG-aaa"]
    assert Settings(coingecko_api_key="").coingecko_api_keys == []
