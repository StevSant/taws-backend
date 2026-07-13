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

    async def get_by_chat_id(self, chat_id: str) -> list[UserBot]:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").eq("chat_id", chat_id).execute()
        return [user_bot_from_row(row) for row in response.data]

    async def get_all(self) -> list[UserBot]:
        client = await self._clients.get()
        response = await client.table(_TABLE).select("*").execute()
        return [user_bot_from_row(row) for row in response.data]

    async def save(self, bot: UserBot) -> UserBot:
        client = await self._clients.get()
        row = {
            "user_id": bot.user_id,
            "bot_token": bot.bot_token,
            "bot_username": bot.bot_username,
            "chat_id": bot.chat_id,
        }
        # Upsert on user_id (the table's unique constraint) -- re-registering (e.g.
        # linking a different bot, or retrying) must replace the existing row instead
        # of raising a 23505 duplicate-key error.
        response = await client.table(_TABLE).upsert(row, on_conflict="user_id").execute()
        return user_bot_from_row(response.data[0])

    async def delete(self, user_id: str) -> None:
        client = await self._clients.get()
        await client.table(_TABLE).delete().eq("user_id", user_id).execute()
