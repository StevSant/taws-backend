import functools

from jwt import PyJWKClient


@functools.lru_cache(maxsize=8)
def get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Return a process-wide `PyJWKClient` for a JWKS URL, reused across requests.

    `PyJWKClient` caches the fetched signing keys internally, so a single instance per
    URL avoids refetching the JWKS on every request. Cached by URL via `lru_cache` — do
    NOT construct a new client per request.

    The Supabase JWKS endpoint (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) is public
    and served without an `apikey` header (verified: bare GET returns 200), so no custom
    headers are configured here.
    """
    return PyJWKClient(jwks_url)
