from datetime import UTC, datetime

from app.domain.telegram.entities import TelegramLinkToken
from app.domain.telegram.ports import TelegramLinkTokenRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.telegram_link_token_row_mapper import (
    telegram_link_token_from_row,
)

_TABLE = "telegram_link_tokens"


class SupabaseTelegramLinkTokenRepository(TelegramLinkTokenRepository):
    """TelegramLinkTokenRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `migrations/versions/0004_telegram_links.py` for the schema
    (`telegram_link_tokens`) and its RLS policies.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def create(self, token: TelegramLinkToken) -> TelegramLinkToken:
        client = await self._clients.get()
        response = (
            await client.table(_TABLE)
            .insert(
                {
                    "token": token.token,
                    "user_id": token.user_id,
                    "expires_at": token.expires_at.isoformat(),
                    "created_at": token.created_at.isoformat(),
                }
            )
            .execute()
        )
        return telegram_link_token_from_row(response.data[0])

    async def consume(self, token: str) -> TelegramLinkToken | None:
        client = await self._clients.get()
        now_iso = datetime.now(UTC).isoformat()
        # Single conditional UPDATE (not read-then-write): only matches a row that is
        # both unconsumed and unexpired, so two concurrent callers racing on the same
        # token can never both succeed — PostgREST returns the updated row only to the
        # request that actually matched it.
        response = (
            await client.table(_TABLE)
            .update({"consumed_at": now_iso})
            .eq("token", token)
            .is_("consumed_at", "null")
            .gt("expires_at", now_iso)
            .execute()
        )
        return telegram_link_token_from_row(response.data[0]) if response.data else None
