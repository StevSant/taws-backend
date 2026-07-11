from abc import ABC, abstractmethod

from app.domain.telegram.entities import TelegramLink


class TelegramLinkRepository(ABC):
    """Port for persisting verified `user_id` <-> Telegram `chat_id` links.

    Consumed by `TelegramNotificationChannel` (resolves a watchlist owner's linked
    chat before delivering an alert) and by the linking API endpoints
    (`api/v1/routers/telegram.py`).
    """

    @abstractmethod
    async def get_by_user_id(self, user_id: str) -> TelegramLink | None:
        """Return the Telegram link for this user, or `None` if they haven't linked."""
        raise NotImplementedError

    @abstractmethod
    async def link(self, link: TelegramLink) -> TelegramLink:
        """Persist `link`, replacing any existing link for the same `user_id` or the
        same `chat_id` (unlink-then-relink semantics — see `TelegramLink`'s docstring
        for why this is simpler than an update-in-place across two unique constraints).
        """
        raise NotImplementedError

    @abstractmethod
    async def unlink(self, user_id: str) -> None:
        """Remove the Telegram link for this user, if any. A no-op if they have none."""
        raise NotImplementedError
