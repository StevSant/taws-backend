from supabase import AsyncClient

from app.infrastructure.persistence.build_supabase_client import build_supabase_client


class SupabaseClientCache:
    """Lazily builds and caches one `AsyncClient` per owning adapter instance.

    Composed (not inherited) by each Supabase-backed repository adapter so the
    client construction/caching logic isn't duplicated across `Supabase*Repository`
    classes. The `Container` already caches each repository as a process-wide
    singleton, so in practice the underlying client is built once per adapter.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key
        self._client: AsyncClient | None = None

    async def get(self) -> AsyncClient:
        if self._client is None:
            self._client = await build_supabase_client(self._supabase_url, self._supabase_key)
        return self._client
