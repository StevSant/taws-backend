from typing import Any

from app.domain.telegram.entities import UserBot


def user_bot_from_row(row: Any) -> UserBot:
    """Map one `user_bots` table row (as returned by `supabase-py`) onto `UserBot`."""
    return UserBot(
        id=row["id"],
        user_id=row["user_id"],
        bot_token=row["bot_token"],
        bot_username=row["bot_username"],
        chat_id=row["chat_id"],
    )
