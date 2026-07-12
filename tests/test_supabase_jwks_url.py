"""Unit tests for `supabase_jwks_url` — builds the project's JWKS endpoint URL.

The URL is derived from `settings.supabase_url` (never hardcoded) and must be
trailing-slash safe so a configured base with or without a trailing "/" yields the
same, single-slash JWKS URL.
"""

from app.api.v1.dependencies.supabase_jwks_url import supabase_jwks_url


def test_builds_jwks_url_from_base() -> None:
    assert (
        supabase_jwks_url("https://abc.supabase.co")
        == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_is_trailing_slash_safe() -> None:
    assert (
        supabase_jwks_url("https://abc.supabase.co/")
        == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"
    )
