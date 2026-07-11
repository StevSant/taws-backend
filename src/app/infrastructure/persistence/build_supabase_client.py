from supabase import AsyncClient, create_async_client

# Supabase's new-format key prefix that unambiguously identifies a publishable/anon key
# (as opposed to `sb_secret_...`, the service-role key). Legacy JWT-format keys (`eyJ...`)
# aren't checked here — the role claim lives inside the JWT payload, not the prefix.
_PUBLISHABLE_KEY_PREFIX = "sb_publishable_"


async def build_supabase_client(supabase_url: str | None, supabase_key: str | None) -> AsyncClient:
    """Build an async `supabase-py` client from the configured project URL + API key.

    Raises `RuntimeError` when either is missing, so callers should invoke this
    lazily — on the first real operation, not at DI-wiring/app-boot time — the same
    "fail on use, not on boot" convention every other vendor adapter in this codebase
    follows (e.g. `PgvectorStore`), so the app still boots without Supabase configured.

    Also raises `RuntimeError` if `supabase_key` is a publishable/anon key (issue #31):
    this backend is architected to bypass RLS via the service-role key (see migration
    0001's rationale), so a publishable key here would otherwise pass this check silently
    and only surface many requests later as a confusing `42501` RLS violation on the
    first real write.
    """
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Supabase is not configured — set SUPABASE_URL and SUPABASE_KEY to use this feature."
        )
    if supabase_key.startswith(_PUBLISHABLE_KEY_PREFIX):
        raise RuntimeError(
            "SUPABASE_KEY is a publishable (anon) key — this backend requires the "
            "service-role (secret) key to bypass RLS by design. Get the 'service_role' "
            "secret from Project Settings -> API in the Supabase dashboard."
        )
    return await create_async_client(supabase_url, supabase_key)
