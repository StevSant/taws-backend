from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class TelegramLink:
    """A verified `user_id` <-> Telegram `chat_id` mapping (issue #14 per-user linking).

    Created once the `/start <token>` deep-link flow validates a pending
    `TelegramLinkToken` (see `telegram_link_token.py`). At most one row per `user_id`
    and per `chat_id` — enforced at the DB layer (migration `0004_telegram_links`) and
    by `TelegramLinkRepository.link`'s unlink-then-relink semantics, so relinking a user
    to a new chat (or a chat to a new user) never leaves a stale duplicate behind.
    """

    user_id: str
    chat_id: str
    linked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
