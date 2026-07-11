from typing import Any

from app.domain.telegram.entities import TelegramLinkToken
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def telegram_link_token_from_row(row: Any) -> TelegramLinkToken:
    """Map one `telegram_link_tokens` table row onto `TelegramLinkToken`."""
    return TelegramLinkToken(
        token=row["token"],
        user_id=row["user_id"],
        expires_at=parse_supabase_timestamp(row["expires_at"]),
        consumed_at=parse_supabase_timestamp(row["consumed_at"]) if row["consumed_at"] else None,
        created_at=parse_supabase_timestamp(row["created_at"]),
    )
