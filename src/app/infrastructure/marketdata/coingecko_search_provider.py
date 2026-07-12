import logging
import time
from typing import Any

import httpx

from app.domain.market.entities import CoinCandidate
from app.domain.market.ports import CoinGeckoSearchProvider

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
        api_key: str | None = None,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key or None
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float | None = None

    async def search(self, query: str) -> list[CoinCandidate]:
        if self._in_cooldown():
            return []

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds, headers=self._headers()
            ) as client:
                response = await client.get("/search", params={"query": query})
                response.raise_for_status()
                payload = response.json()
            return [_to_candidate(hit) for hit in payload.get("coins", [])]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            # `ValueError` covers `json.JSONDecodeError` (malformed body on a 200);
            # `KeyError`/`TypeError`/`AttributeError` cover an unexpected hit shape
            # (missing `id`/`symbol`/`name`, or `payload`/`hit` not being a dict).
            self._enter_cooldown(error)
            return []

    def _headers(self) -> dict[str, str]:
        return {"x-cg-demo-api-key": self._api_key} if self._api_key else {}

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
