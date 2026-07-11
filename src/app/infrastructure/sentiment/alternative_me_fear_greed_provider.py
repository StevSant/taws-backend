from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.ports import FearGreedProvider
from app.infrastructure.sentiment.parse_fear_greed_classification import (
    parse_fear_greed_classification,
)


class AlternativeMeFearGreedProvider(FearGreedProvider):
    """FearGreedProvider adapter backed by alternative.me's free, no-auth-required Crypto
    Fear & Greed Index API (`GET {base_url}/fng/`).

    No API key required — same "free public API, no key" shape as `CoinGeckoMarketDataProvider`.
    Callers should wrap this in `RoutingFearGreedProvider` rather than using it directly, so
    any failure (network error, malformed payload, an unrecognized classification label)
    falls back to `FixtureFearGreedProvider` instead of raising.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds

    async def get_fear_greed_index(self) -> FearGreedReading:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.get("/fng/", params={"limit": 1, "format": "json"})
            response.raise_for_status()
            payload = response.json()

        return _to_reading(payload)


def _to_reading(payload: dict[str, Any]) -> FearGreedReading:
    data = payload.get("data") or []
    if not data:
        raise RuntimeError("[AlternativeMeFearGreedProvider] No data returned by alternative.me.")
    latest = data[0]
    return FearGreedReading(
        value=int(latest["value"]),
        classification=parse_fear_greed_classification(latest["value_classification"]),
        as_of=datetime.fromtimestamp(int(latest["timestamp"]), tz=UTC),
    )
