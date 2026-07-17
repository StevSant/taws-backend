import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from typing import Any

from supabase import AsyncClient

from app.domain.agents.entities import Message
from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository
from app.infrastructure.persistence.conversation_message_row_mapper import (
    conversation_message_from_row,
)
from app.infrastructure.persistence.conversation_row_mapper import conversation_from_row
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

logger = logging.getLogger(__name__)

_CONVERSATIONS_TABLE = "conversations"
_MESSAGES_TABLE = "conversation_messages"

# The columns of a sidebar summary — everything except the turns, which live in their own
# table. Spelled out rather than `select("*")` so the listing query can never accidentally
# start dragging a joined payload along.
_SUMMARY_COLUMNS = "id, user_id, title, created_at, updated_at"


class SupabaseConversationRepository(ConversationRepository):
    """ConversationRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `backend/migrations/versions/0020_conversations.py` for the `conversations` /
    `conversation_messages` schema and its RLS policies (owner-only, scoped to `auth.uid()`).
    Every `.execute()` call is wrapped in `with_supabase_retry` (issue #7) — same shape and
    rationale as `SupabaseNoteRepository`.

    This class used to be a stub holding an in-process `dict`, which is why chat history
    never reached the database: writes went to RAM and died with the worker.
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

    async def get(self, conversation_id: str) -> Conversation | None:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_CONVERSATIONS_TABLE).select("*").eq("id", conversation_id).execute()
            )
        )
        if not response.data:
            return None

        message_response = await self._retry(
            lambda: (
                client.table(_MESSAGES_TABLE)
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("ordinal")
                .execute()
            )
        )
        messages = [conversation_message_from_row(row) for row in message_response.data]
        return conversation_from_row(response.data[0], messages)

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        client = await self._clients.get()
        response = await self._retry(
            lambda: (
                client.table(_CONVERSATIONS_TABLE)
                .select(_SUMMARY_COLUMNS)
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .execute()
            )
        )
        return [conversation_from_row(row) for row in response.data]

    async def ensure(self, conversation_id: str, user_id: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_CONVERSATIONS_TABLE)
                .upsert(
                    {"id": conversation_id, "user_id": user_id},
                    ignore_duplicates=True,
                )
                .execute()
            )
        )

    async def append_messages(self, conversation_id: str, messages: Sequence[Message]) -> None:
        if not messages:
            return

        client = await self._clients.get()
        first_ordinal = await self._next_ordinal(client, conversation_id)
        rows = [
            self._to_row(conversation_id, message, first_ordinal + offset)
            for offset, message in enumerate(messages)
        ]
        await self._retry(lambda: client.table(_MESSAGES_TABLE).insert(rows).execute())
        # The insert above has already COMMITTED the turn; `_touch` only bumps `updated_at` for
        # the sidebar's most-recently-updated ordering (cosmetic). A transient failure here must
        # NOT bubble up: `StreamAndPersistReply`'s retry loop would re-run this whole method and
        # re-insert the turn at fresh ordinals, duplicating the user+assistant pair — the
        # non-atomic insert+touch edge both this class's and that use case's docstrings note. So
        # swallow a post-insert touch failure with a warning: a slightly stale sidebar order is
        # strictly better than a duplicated ("phantom") turn.
        try:
            await self._touch(client, conversation_id)
        except Exception:  # noqa: BLE001 — turn already committed; a touch failure is cosmetic
            logger.warning(
                "updated_at bump (_touch) failed for conversation %r after the turn was already "
                "inserted; leaving updated_at stale to avoid a duplicate-turn re-insert",
                conversation_id,
                exc_info=True,
            )

    async def update_title(self, conversation_id: str, title: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_CONVERSATIONS_TABLE)
                .update({"title": title, "updated_at": datetime.now(UTC).isoformat()})
                .eq("id", conversation_id)
                .execute()
            )
        )

    async def delete(self, conversation_id: str) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: client.table(_CONVERSATIONS_TABLE).delete().eq("id", conversation_id).execute()
        )

    @staticmethod
    def _to_row(conversation_id: str, message: Message, ordinal: int) -> dict[str, Any]:
        """Build the `conversation_messages` insert row for one turn.

        `charts` is included ONLY when the turn carries charts (an assistant reply that drew
        something). Omitting the key for the common text-only turn keeps writes working even
        against a database where the `charts` column has not been added yet — and stores NULL
        rather than an empty `[]` when there is nothing to persist.
        """
        row: dict[str, Any] = {
            "conversation_id": conversation_id,
            "role": message.role.value,
            "content": message.content,
            "ordinal": ordinal,
        }
        if message.charts:
            row["charts"] = message.charts
        if message.citations:
            row["citations"] = message.citations
        return row

    async def _next_ordinal(self, client: AsyncClient, conversation_id: str) -> int:
        """Return the ordinal the next appended message should take.

        Read-then-write, so two concurrent appends to the SAME thread could compute the
        same ordinal. That is bounded rather than silent: `conversation_messages` is unique
        on `(conversation_id, ordinal)`, so the loser's insert fails loudly instead of
        overwriting or duplicating a turn. Concurrent turns on one thread aren't a flow the
        UI can produce today (the composer is disabled while a reply streams).
        """
        response = await self._retry(
            lambda: (
                client.table(_MESSAGES_TABLE)
                .select("ordinal")
                .eq("conversation_id", conversation_id)
                .order("ordinal", desc=True)
                .limit(1)
                .execute()
            )
        )
        if not response.data:
            return 0
        # `postgrest` types its rows as the broad `JSON` union, which pyright won't narrow
        # to `dict` on its own — the same reason every `*_row_mapper` takes `row: Any`.
        highest: Any = response.data[0]
        return int(highest["ordinal"]) + 1

    async def _touch(self, client: AsyncClient, conversation_id: str) -> None:
        """Bump `updated_at` so the sidebar's most-recently-updated-first order is right."""
        await self._retry(
            lambda: (
                client.table(_CONVERSATIONS_TABLE)
                .update({"updated_at": datetime.now(UTC).isoformat()})
                .eq("id", conversation_id)
                .execute()
            )
        )
