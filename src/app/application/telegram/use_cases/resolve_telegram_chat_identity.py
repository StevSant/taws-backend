import logging

from app.domain.profile.ports import UserProfileRepository
from app.domain.telegram.ports import TelegramLinkRepository

logger = logging.getLogger(__name__)


class ResolveTelegramChatIdentity:
    """Resolve an inbound Telegram `chat_id` to the acting `(user_id, locale)` for chat.

    The Telegram chat handler used to stream every turn as `user_id=""` in a fixed locale,
    so per-user tools (watchlist, etc.) never worked over Telegram even for a linked account.
    This resolves the chat back to its linked user via `TelegramLinkRepository.get_by_chat_id`
    and reads that user's `preferred_locale` from `UserProfileRepository`:

    - linked   -> (the linked `user_id`, the user's `preferred_locale` or `default_locale`)
    - unlinked -> (`""`, `default_locale`)

    A profile-lookup failure degrades to `default_locale` rather than failing the turn —
    which language to answer in is never worth dropping a reply over (same stance as
    `ResolveLocale`)."""

    def __init__(
        self,
        link_repository: TelegramLinkRepository,
        user_profile_repository: UserProfileRepository,
        default_locale: str,
    ) -> None:
        self._link_repository = link_repository
        self._user_profile_repository = user_profile_repository
        self._default_locale = default_locale

    async def execute(self, chat_id: str) -> tuple[str, str]:
        link = await self._link_repository.get_by_chat_id(chat_id)
        if link is None:
            return "", self._default_locale

        try:
            profile = await self._user_profile_repository.get(link.user_id)
        except Exception:  # noqa: BLE001 — never fail a Telegram turn over a locale lookup
            logger.warning(
                "Failed to read the profile for Telegram-linked user %r",
                link.user_id,
                exc_info=True,
            )
            profile = None

        if profile is not None and profile.preferred_locale:
            return link.user_id, profile.preferred_locale
        return link.user_id, self._default_locale
