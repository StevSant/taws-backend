import time


class TtlCache[K, V]:
    """Minimal in-process TTL cache (`get`/`set`), entries expire after `ttl_seconds`.

    Not thread-safe beyond the GIL and not distributed/shared across processes — that's
    fine here: it's meant to sit in front of a handful of idempotent, side-effect-free
    read calls to a rate-limited third-party API within a single process (see
    `CoinGeckoMarketDataProvider`, issue #8), not to serve as a general-purpose or
    multi-instance cache. No eviction policy beyond TTL expiry (checked lazily on
    `get`), since the tiny key space this is used for (a handful of `(coin_id, days)`
    pairs) never needs one.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: K, value: V) -> None:
        self._store[key] = (time.monotonic() + self._ttl_seconds, value)
