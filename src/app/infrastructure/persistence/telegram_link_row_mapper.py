from typing import Any

from app.domain.telegram.entities import TelegramLink
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def telegram_link_from_row(row: Any) -> TelegramLink:
    """Map one `telegram_links` table row (as returned by `supabase-py`) onto `TelegramLink`."""
    return TelegramLink(
        user_id=row["user_id"],
        chat_id=row["telegram_chat_id"],
        linked_at=parse_supabase_timestamp(row["linked_at"]),
    )
