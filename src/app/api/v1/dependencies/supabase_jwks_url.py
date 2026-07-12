def supabase_jwks_url(supabase_url: str) -> str:
    """Build the project's JWKS endpoint URL from the Supabase base URL.

    Trailing-slash safe so a configured base with or without a trailing "/" yields the
    same single-slash URL. The base itself comes from `settings.supabase_url` — never
    hardcode the project ref here.
    """
    return f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
