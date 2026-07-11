from supabase import AsyncClient, create_async_client


async def build_supabase_client(supabase_url: str | None, supabase_key: str | None) -> AsyncClient:
    """Build an async `supabase-py` client from the configured project URL + API key.

    Raises `RuntimeError` when either is missing, so callers should invoke this
    lazily — on the first real operation, not at DI-wiring/app-boot time — the same
    "fail on use, not on boot" convention every other vendor adapter in this codebase
    follows (e.g. `PgvectorStore`), so the app still boots without Supabase configured.
    """
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Supabase is not configured — set SUPABASE_URL and SUPABASE_KEY to use this feature."
        )
    return await create_async_client(supabase_url, supabase_key)
