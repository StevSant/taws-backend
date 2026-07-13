from typing import Any

from app.domain.agents.entities import Message
from app.domain.chat.entities import Conversation
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def conversation_from_row(row: Any, messages: list[Message] | None = None) -> Conversation:
    """Map one `conversations` table row (as returned by `supabase-py`) onto `Conversation`.

    `messages` is passed separately because the turns live in their own table: the sidebar
    listing loads rows without them (`messages=None` -> empty list), while `get` loads a
    thread's `conversation_messages` and hands them in.

    Typed `Any` rather than `dict[str, Any]`: `postgrest`'s response rows are typed as the
    broad `JSON` union, which pyright won't narrow to `dict` automatically — same rationale
    as `note_row_mapper.py`.
    """
    return Conversation(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        messages=messages if messages is not None else [],
        created_at=parse_supabase_timestamp(row["created_at"]),
        updated_at=parse_supabase_timestamp(row["updated_at"]),
    )
