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
    async def get_by_chat_id(self, chat_id: str) -> TelegramLink | None:
        """Return the Telegram link for this chat_id, or `None` if this chat hasn't
        linked to any user.

        The REVERSE lookup direction from `get_by_user_id` (issue #19's `/briefing`,
        `/signal`, `/simular` inbound commands): a webhook update only carries the
        Telegram `chat_id` that sent it, and every one of those commands needs to
        resolve it back to the `user_id` whose data to fetch. `get_by_user_id` stays
        the OUTBOUND direction used by `TelegramNotificationChannel` to resolve a
        watchlist owner to their linked chat before delivering an alert.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[TelegramLink]:
        """Return every link in the store — the BROADCAST direction.

        Exists for broadcast delivery: fan a single message out to every linked chat,
        rather than resolving one specific recipient (`get_by_user_id` / `get_by_chat_id`).
        Consumed by `/event-intelligence/demo` and `/telegram/send-test-news`, which push
        one enriched market event over the shared bot to everyone who has linked.
        """
        raise NotImplementedError

    @abstractmethod
    async def link(self, link: TelegramLink) -> TelegramLink:
        """Persist `link`, replacing any existing link for the same `user_id` or the
        same `chat_id` (unlink-then-relink semantics — see `TelegramLink`'s docstring
        for why this is simpler than an update-in-place across two unique constraints).

        Implementations must make the replace-then-insert atomic with respect to other
        concurrent `link()` calls racing on the same `user_id` or `chat_id` — see
        `SupabaseTelegramLinkRepository.link`'s docstring and migration
        `0005_telegram_links_atomic_relink` for how the Supabase adapter satisfies this
        (a DB-side trigger, not an app-layer multi-call sequence).
        """
        raise NotImplementedError

    @abstractmethod
    async def unlink(self, user_id: str) -> None:
        """Remove the Telegram link for this user, if any. A no-op if they have none."""
        raise NotImplementedError
