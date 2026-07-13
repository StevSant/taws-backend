import logging
import time
from typing import Any

import httpx

from app.domain.market.entities import CoinCandidate
from app.domain.market.ports import CoinGeckoSearchProvider
from app.infrastructure.marketdata.coingecko_get import coingecko_get
from app.infrastructure.marketdata.coingecko_key_ring import CoinGeckoKeyRing
from app.infrastructure.marketdata.coingecko_rate_limited_error import CoinGeckoRateLimitedError

logger = logging.getLogger(__name__)


class CoinGeckoCoinSearchProvider(CoinGeckoSearchProvider):
    """CoinGeckoSearchProvider adapter backed by CoinGecko's public `/search` endpoint.

    Reuses the exact cooldown/circuit-breaker shape from
    `CoinGeckoMarketDataProvider` (issue #8): once a live call fails (rate-limited
    or unreachable), back off for `cooldown_seconds` and return `[]` on every
    subsequent `search()` call instead of hammering the API — search degrades to
    "no results" rather than crashing (instrument-search spec's "fails soft").

    "Fails soft" also covers a MALFORMED 200 response (MEDIUM fix, post-hoc
    adversarial review): a body that isn't valid JSON, or hits missing the keys
    `_to_candidate` expects, must also degrade to `[]` instead of propagating
    `json.JSONDecodeError`/`KeyError` up into a 500 on `GET /instruments/search`.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        key_ring: CoinGeckoKeyRing | None = None,
        cooldown_seconds: float = 300.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._key_ring = key_ring or CoinGeckoKeyRing([])
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float | None = None
        # Shared pooled client threaded through `coingecko_get` (issue #71 perf); `None` keeps
        # the per-call client behavior used by the failover unit tests. See `coingecko_get`.
        self._http_client = http_client

    async def search(self, query: str) -> list[CoinCandidate]:
        if self._in_cooldown():
            return []

        try:
            payload = await coingecko_get(
                base_url=self._base_url,
                path="/search",
                params={"query": query},
                timeout_seconds=self._timeout_seconds,
                key_ring=self._key_ring,
                http_client=self._http_client,
            )
            return [_to_candidate(hit) for hit in payload.get("coins", [])]
        except CoinGeckoRateLimitedError:
            # Every key is throttled; the ring is already timing their comeback. "Fails soft"
            # to no results WITHOUT arming the breaker on top of it.
            return []
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            # `ValueError` covers `json.JSONDecodeError` (malformed body on a 200);
            # `KeyError`/`TypeError`/`AttributeError` cover an unexpected hit shape
            # (missing `id`/`symbol`/`name`, or `payload`/`hit` not being a dict).
            self._enter_cooldown(error)
            return []

    def _in_cooldown(self) -> bool:
        if self._cooldown_until is None:
            return False
        if time.monotonic() >= self._cooldown_until:
            self._cooldown_until = None
            return False
        return True

    def _enter_cooldown(self, error: Exception) -> None:
        self._cooldown_until = time.monotonic() + self._cooldown_seconds
        logger.warning(
            "CoinGecko search unavailable (%s); backing off for %.0fs and returning no results.",
            error,
            self._cooldown_seconds,
        )


def _to_candidate(hit: dict[str, Any]) -> CoinCandidate:
    return CoinCandidate(
        id=hit["id"],
        symbol=hit["symbol"],
        name=hit["name"],
        market_cap_rank=hit.get("market_cap_rank"),
        thumb=hit.get("thumb", ""),
    )
