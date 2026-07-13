from datetime import UTC, datetime
from functools import partial

from app.domain.profile.entities import UserProfile
from app.domain.profile.ports import UserProfileRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.user_profile_row_mapper import user_profile_from_row
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_PROFILES_TABLE = "profiles"


class SupabaseUserProfileRepository(UserProfileRepository):
    """UserProfileRepository adapter backed by Supabase Postgres via `supabase-py` (issue #67).

    See `backend/migrations/versions/0017_user_profiles.py` for the `profiles` schema and its
    RLS policies (owner-only, scoped to `auth.uid()`). Every `.execute()` call is wrapped in
    `with_supabase_retry` (issue #7) — same shape and rationale as `SupabaseNoteRepository`.
    """

    def __init__(
        self,
        supabase_url: str | None,
        supabase_key: str | None,
        retry_max_attempts: int = 2,
        retry_backoff_base_seconds: float = 0.2,
    ) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)
        self._retry = partial(
            with_supabase_retry,
            max_attempts=retry_max_attempts,
            backoff_base_seconds=retry_backoff_base_seconds,
        )

    async def get(self, user_id: str) -> UserProfile | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_PROFILES_TABLE).select("*").eq("user_id", user_id).execute()
        )
        return user_profile_from_row(response.data[0]) if response.data else None

    async def set_preferred_locale(self, user_id: str, preferred_locale: str | None) -> UserProfile:
        client = await self._clients.get()
        now = datetime.now(UTC).isoformat()
        response = await self._retry(
            lambda: (
                client.table(_PROFILES_TABLE)
                .upsert(
                    {
                        "user_id": user_id,
                        "preferred_locale": preferred_locale,
                        "updated_at": now,
                    },
                    on_conflict="user_id",
                )
                .execute()
            )
        )
        return user_profile_from_row(response.data[0])
