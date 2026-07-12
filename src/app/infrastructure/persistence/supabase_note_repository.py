from datetime import UTC, datetime
from functools import partial

from app.domain.notes.entities import Note
from app.domain.notes.ports import NoteRepository
from app.infrastructure.persistence.note_row_mapper import note_from_row
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_NOTES_TABLE = "user_notes"


class SupabaseNoteRepository(NoteRepository):
    """NoteRepository adapter backed by Supabase Postgres via `supabase-py` (issue #62).

    See `backend/migrations/0011_user_notes.py` for the `user_notes` schema and its RLS
    policies (owner-only, scoped to `auth.uid()`). Every `.execute()` call is wrapped in
    `with_supabase_retry` (issue #7) — same shape and rationale as
    `SupabaseWatchlistRepository`.
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

    async def list_for_user(self, user_id: str) -> list[Note]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_NOTES_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .execute()
            )
        )
        return [note_from_row(row) for row in response.data]

    async def get(self, note_id: str) -> Note | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: client.table(_NOTES_TABLE).select("*").eq("id", note_id).execute()
        )
        return note_from_row(response.data[0]) if response.data else None

    async def create(self, note: Note) -> Note:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_NOTES_TABLE)
                .insert(
                    {
                        "id": note.id,
                        "user_id": note.user_id,
                        "body": note.body,
                        "created_at": note.created_at.isoformat(),
                        "updated_at": note.updated_at.isoformat(),
                    }
                )
                .execute()
            )
        )
        return note_from_row(response.data[0])

    async def update(self, note_id: str, body: str) -> Note:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_NOTES_TABLE)
                .update({"body": body, "updated_at": datetime.now(UTC).isoformat()})
                .eq("id", note_id)
                .execute()
            )
        )
        return note_from_row(response.data[0])

    async def delete(self, note_id: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: client.table(_NOTES_TABLE).delete().eq("id", note_id).execute()
        )
