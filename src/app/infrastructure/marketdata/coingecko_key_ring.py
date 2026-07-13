import logging
import time
from collections.abc import Iterator, Sequence

logger = logging.getLogger(__name__)

_API_KEY_HEADER = "x-cg-demo-api-key"


class CoinGeckoKeyRing:
    """Ordered pool of CoinGecko Demo API keys, with per-key failover on rate limits.

    CoinGecko's Demo tier meters its quota PER KEY (~30 calls/min, 10k/month), and this
    backend spends that one quota from three different adapters at once
    (`CoinGeckoMarketDataProvider`, `CoinGeckoInstrumentMetadataProvider`,
    `CoinGeckoCoinSearchProvider`). One ring instance is therefore shared by all three
    (built once in `Container.get_coingecko_key_ring()`), so a 429 seen while fetching
    prices also steers the metadata and search calls off that same exhausted key —
    a per-adapter ring would each have to rediscover the rate limit on their own.

    Keys are tried in order. A key that 429s is BENCHED for `key_cooldown_seconds` and
    skipped by subsequent calls, so the next request goes straight to the next key
    instead of paying a wasted round trip to re-learn it is throttled. The bench is
    self-clearing: the Demo limit is per-minute, so a benched key rejoins the ring on
    its own once the window rolls over.

    With NO keys configured the ring still yields exactly one attempt — sending no auth
    header at all (the keyless public API). That slot benches on a 429 like any other,
    which is what keeps a keyless deployment from hammering CoinGecko once it is
    throttled.
    """

    def __init__(self, api_keys: Sequence[str], key_cooldown_seconds: float = 60.0) -> None:
        self._api_keys = [key.strip() for key in api_keys if key.strip()]
        self._key_cooldown_seconds = key_cooldown_seconds
        self._benched_until: dict[int, float] = {}

    def attempts(self) -> Iterator[tuple[int, dict[str, str]]]:
        """Yield `(slot, headers)` for every key not currently benched, in priority order.

        Yields nothing when every key is benched — `coingecko_get` turns that into a
        `CoinGeckoRateLimited` without making any HTTP call at all, which IS the backoff.
        """
        for slot in range(self._slot_count()):
            if self._is_benched(slot):
                continue
            yield slot, self._headers(slot)

    def bench(self, slot: int) -> None:
        """Take a rate-limited key out of rotation until its per-minute window rolls over."""
        self._benched_until[slot] = time.monotonic() + self._key_cooldown_seconds
        logger.warning(
            "CoinGecko rate-limited %s; benching it for %.0fs and failing over to the "
            "next key (%d configured).",
            self._describe(slot),
            self._key_cooldown_seconds,
            len(self._api_keys),
        )

    def _slot_count(self) -> int:
        """One slot per key, or a single keyless slot when none are configured."""
        return len(self._api_keys) or 1

    def _headers(self, slot: int) -> dict[str, str]:
        if not self._api_keys:
            return {}
        return {_API_KEY_HEADER: self._api_keys[slot]}

    def _is_benched(self, slot: int) -> bool:
        benched_until = self._benched_until.get(slot)
        if benched_until is None:
            return False
        if time.monotonic() >= benched_until:
            del self._benched_until[slot]
            return False
        return True

    def _describe(self, slot: int) -> str:
        """Name a key for logs WITHOUT leaking it — position in the ring, never the value."""
        if not self._api_keys:
            return "the keyless public API"
        return f"API key #{slot + 1}"
