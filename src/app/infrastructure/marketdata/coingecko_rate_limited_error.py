class CoinGeckoRateLimitedError(Exception):
    """Every configured CoinGecko API key is currently rate-limited (429).

    Raised by `coingecko_get` when it has no key left to try — either every key 429'd
    during this call, or they were all already benched by `CoinGeckoKeyRing` from a
    recent 429. Distinct from a plain `httpx.HTTPError` on purpose: a rate limit means
    "wait for a key to come back", which the key ring is already timing, so the adapters
    degrade (empty series / no metadata / no search hits) WITHOUT also tripping their own
    long provider-wide cooldown on top of it.
    """
