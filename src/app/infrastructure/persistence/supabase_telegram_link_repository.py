from app.domain.telegram.entities import TelegramLink
from app.domain.telegram.ports import TelegramLinkRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.telegram_link_row_mapper import telegram_link_from_row

_TABLE = "telegram_links"


class SupabaseTelegramLinkRepository(TelegramLinkRepository):
    """TelegramLinkRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0004_telegram_links.py` for the schema (`telegram_links`,
    unique on both `user_id` and `telegram_chat_id`) and its RLS policies.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def get_by_user_id(self, user_id: str) -> TelegramLink | None:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").eq("user_id", user_id).execute()
        return telegram_link_from_row(response.data[0]) if response.data else None

    async def link(self, link: TelegramLink) -> TelegramLink:
        client = await self._clients.get()
        # Unlink-then-relink: clears any prior row for this user AND any prior row for
        # this chat_id, so the two unique constraints (`user_id`, `telegram_chat_id`)
        # never conflict on insert — see `TelegramLinkRepository.link`'s docstring.
        await client.table(_TABLE).delete().eq("user_id", link.user_id).execute()
        await client.table(_TABLE).delete().eq("telegram_chat_id", link.chat_id).execute()
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
