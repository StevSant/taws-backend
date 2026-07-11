from app.domain.telegram.entities import TelegramLink
from app.domain.telegram.ports import TelegramLinkRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.telegram_link_row_mapper import telegram_link_from_row

_TABLE = "telegram_links"


class SupabaseTelegramLinkRepository(TelegramLinkRepository):
    """TelegramLinkRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0004_telegram_links.py` for the schema (`telegram_links`,
    unique on both `user_id` and `telegram_chat_id`) and its RLS policies, and
    `migrations/versions/0005_telegram_links_atomic_relink.py` for the `BEFORE INSERT`
    trigger `link()` relies on for atomicity (see that method's docstring).
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def get_by_user_id(self, user_id: str) -> TelegramLink | None:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").eq("user_id", user_id).execute()
        return telegram_link_from_row(response.data[0]) if response.data else None

    async def link(self, link: TelegramLink) -> TelegramLink:
        client = await self._clients.get()
        # Unlink-then-relink used to be two separate `delete` calls issued from here,
        # each its own auto-committing PostgREST transaction — that let two concurrent
        # `link()` calls racing on the same `telegram_chat_id` (or `user_id`) interleave
        # and silently drop one caller's just-inserted row (see migration 0005's
        # docstring for the full race). The delete is now performed atomically, inside
        # the SAME transaction as this insert and under an advisory lock, by a
        # `BEFORE INSERT` trigger on `telegram_links` — this method only needs to
        # insert.
        response = (
            await client.table(_TABLE)
            .insert(
                {
                    "user_id": link.user_id,
                    "telegram_chat_id": link.chat_id,
                    "linked_at": link.linked_at.isoformat(),
                }
            )
            .execute()
        )
        return telegram_link_from_row(response.data[0])

    async def unlink(self, user_id: str) -> None:
        client = await self._clients.get()
        await client.table(_TABLE).delete().eq("user_id", user_id).execute()
