"""An injected shared httpx client is reused and never closed by the provider (issue #71).

The container owns ONE `httpx.AsyncClient` pooled across every external HTTP provider and
closes it once on shutdown (`Container.aclose_http_client`). A provider handed that client must
issue its request THROUGH it without closing it — closing the shared pool mid-run would break
every other provider still using it. `AlternativeMeFearGreedProvider` is the simplest injection
site (no API key, no key ring), so it stands in for the shared-client contract here.
"""

import httpx

from app.infrastructure.sentiment import AlternativeMeFearGreedProvider

_FNG_PAYLOAD = {
    "data": [
        {"value": "42", "value_classification": "Fear", "timestamp": "1700000000"},
    ]
}


async def test_injected_client_is_used_and_left_open() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json=_FNG_PAYLOAD)

    shared_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AlternativeMeFearGreedProvider(
        base_url="https://api.alternative.me",
        cache_ttl_seconds=60.0,
        http_client=shared_client,
    )

    reading = await provider.get_fear_greed_index()

    # The request went out on the injected client, against the absolute base_url + path.
    assert reading.value == 42
    assert requested_urls == ["https://api.alternative.me/fng/?limit=1&format=json"]
    # The provider must NOT close the shared client — the container owns its lifetime.
    assert not shared_client.is_closed

    await shared_client.aclose()
