
from app.domain.telegram.entities import UserBot
from app.domain.telegram.ports import UserBotRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.user_bot_row_mapper import user_bot_from_row

_TABLE = "user_bots"


class SupabaseUserBotRepository(UserBotRepository):
    """UserBotRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0009_user_bots.py` for the schema (`user_bots`,
    unique on `user_id`) and its RLS policies.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def get_by_user_id(self, user_id: str) -> UserBot | None:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").eq("user_id", user_id).execute()
        return user_bot_from_row(response.data[0]) if response.data else None

    async def get_by_id(self, bot_id: str) -> UserBot | None:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").eq("id", bot_id).execute()
        return user_bot_from_row(response.data[0]) if response.data else None

    async def save(self, bot: UserBot) -> UserBot:
        client = await self._clients.get()
        row = {
            "user_id": bot.user_id,
            "bot_token": bot.bot_token,
            "bot_username": bot.bot_username,
            "chat_id": bot.chat_id,
        }
        response = await client.table(_TABLE).insert(row).execute()
        return user_bot_from_row(response.data[0])

    async def delete(self, user_id: str) -> None:
        client = await self._clients.get()
        await client.table(_TABLE).delete().eq("user_id", user_id).execute()
