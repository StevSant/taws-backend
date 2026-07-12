"""Unit tests for `get_jwks_client` — the cached `PyJWKClient` factory.

The client (and its underlying signing-key cache) must be reused across requests for the
same JWKS URL rather than rebuilt per call, so verification doesn't refetch the JWKS on
every request. Reuse is provided by `functools.lru_cache`.
"""

from jwt import PyJWKClient

from app.api.v1.dependencies.jwks_client import get_jwks_client

_URL = "https://example.supabase.co/auth/v1/.well-known/jwks.json"


def test_returns_pyjwkclient() -> None:
    get_jwks_client.cache_clear()
    client = get_jwks_client(_URL)
    assert isinstance(client, PyJWKClient)


def test_same_url_returns_cached_instance() -> None:
    get_jwks_client.cache_clear()
    assert get_jwks_client(_URL) is get_jwks_client(_URL)


def test_different_url_returns_different_instance() -> None:
    get_jwks_client.cache_clear()
    other = "https://other.supabase.co/auth/v1/.well-known/jwks.json"
    assert get_jwks_client(_URL) is not get_jwks_client(other)
