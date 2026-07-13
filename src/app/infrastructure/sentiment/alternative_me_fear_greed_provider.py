from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.domain.sentiment.entities import FearGreedReading
from app.domain.sentiment.ports import FearGreedProvider
from app.infrastructure.caching import TtlCache
from app.infrastructure.sentiment.parse_fear_greed_classification import (
    parse_fear_greed_classification,
)


class AlternativeMeFearGreedProvider(FearGreedProvider):
    """FearGreedProvider adapter backed by alternative.me's free, no-auth-required Crypto
    Fear & Greed Index API (`GET {base_url}/fng/`).

    No API key required — same "free public API, no key" shape as `CoinGeckoMarketDataProvider`.
    Callers should wrap this in `RoutingFearGreedProvider` rather than using it directly, so
    any failure (network error, malformed payload, an unrecognized classification label)
    surfaces as `FearGreedUnavailableError`.

    The index only updates ~once a day, yet every sentiment read re-fetched it live, so the
    current reading is held in a short-TTL in-process cache (mirrors
    `CoinGeckoMarketDataProvider`, issue #8). Only a successful read is cached — a network error
    or malformed payload still raises so `RoutingFearGreedProvider` maps it to
    `FearGreedUnavailableError`, never a stale-or-invented value. `cache_ttl_seconds` falls back
    to `Settings.fear_greed_cache_ttl_seconds` when not injected.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: float | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        # Optional shared pooled client (issue #71 perf): when injected, each read reuses its
        # warm connection pool + TLS session instead of opening a fresh client per call, and it
        # is never closed here. `None` keeps the original per-call `httpx.AsyncClient` path.
        self._http_client = http_client
        ttl = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else get_settings().fear_greed_cache_ttl_seconds
        )
        # Single logical reading; keyed by base_url so a reconfigured endpoint gets its own slot.
        self._cache: TtlCache[str, FearGreedReading] = TtlCache(ttl)

    async def get_fear_greed_index(self) -> FearGreedReading:
        cached = self._cache.get(self._base_url)
        if cached is not None:
            return cached

        payload = await self._fetch_index_payload()
        reading = _to_reading(payload)
        self._cache.set(self._base_url, reading)
        return reading

    async def _fetch_index_payload(self) -> dict[str, Any]:
        """GET alternative.me's `/fng/` and return the parsed JSON body.

        Reuses the injected shared pooled client when present (absolute URL + per-request
        timeout, never closing it — issue #71 perf) and otherwise keeps the original per-call
        `httpx.AsyncClient(base_url=..., timeout=...)` behavior.
        """
        params = {"limit": 1, "format": "json"}
        if self._http_client is not None:
            response = await self._http_client.get(
                f"{self._base_url.rstrip('/')}/fng/",
                params=params,
                timeout=self._timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.get("/fng/", params=params)
        response.raise_for_status()
        return response.json()


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
