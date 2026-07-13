from typing import Any

import httpx

from app.infrastructure.marketdata.coingecko_key_ring import CoinGeckoKeyRing
from app.infrastructure.marketdata.coingecko_rate_limited_error import CoinGeckoRateLimitedError


async def coingecko_get(
    *,
    base_url: str,
    path: str,
    params: dict[str, Any] | None,
    timeout_seconds: float,
    key_ring: CoinGeckoKeyRing,
    http_client: httpx.AsyncClient | None = None,
) -> Any:
    """GET a CoinGecko endpoint, failing over to the next API key on a rate limit.

    The single HTTP entry point every CoinGecko adapter goes through, so the failover
    and the shared rate-limit state live in ONE place instead of being re-implemented
    three times. A 429 benches that key on the ring and the SAME request is retried
    immediately on the next one — the caller never sees a rate limit as long as any key
    still has quota.

    Raises `CoinGeckoRateLimitedError` only once no key is left to try (all of them 429'd, or
    were already benched from a recent 429). Every other failure — a 4xx we caused, a 5xx,
    a timeout, a connection error — propagates as the `httpx.HTTPError` it is, because no
    amount of key rotation fixes those and each adapter already handles them.

    When `http_client` is supplied (the container's process-wide pooled client, see
    `Container.get_http_client`), each attempt reuses it — one warm connection pool + TLS
    session instead of a fresh handshake per key attempt — and it is NEVER closed here.
    That shared client carries no `base_url`, headers, or default timeout of its own, so the
    per-key auth `headers` and this call's `timeout` are passed per-request and the URL is
    made absolute. With no client injected (unit tests, direct construction) it keeps the
    original per-attempt `async with httpx.AsyncClient(...)` behavior unchanged.
    """
    for slot, headers in key_ring.attempts():
        if http_client is not None:
            response = await http_client.get(
                f"{base_url.rstrip('/')}{path}",
                params=params,
                headers=headers,
                timeout=timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(
                base_url=base_url, timeout=timeout_seconds, headers=headers
            ) as client:
                response = await client.get(path, params=params)

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            key_ring.bench(slot)
            continue

        response.raise_for_status()
        return response.json()

    raise CoinGeckoRateLimitedError(
        f"every configured CoinGecko API key is rate-limited; {path} not attempted"
    )
