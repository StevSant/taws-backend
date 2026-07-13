import logging

from app.domain.profile.ports import UserProfileRepository

logger = logging.getLogger(__name__)


class ResolveLocale:
    """Resolve the locale an AI-generated reply must be written in (issue #67).

    Precedence, highest first:
    1. the locale the request explicitly asked for (the UI always sends the active one),
    2. the authenticated user's persisted `preferred_locale`,
    3. `Settings.default_locale` (`es`) — anonymous visitors and users who never picked.

    Short-circuits on (1) so the common case costs no database round-trip. A failure while
    reading the profile degrades to `default_locale` instead of propagating: which language
    to answer in is never worth failing a chat turn over.
    """

    def __init__(self, user_profile_repository: UserProfileRepository, default_locale: str) -> None:
        self._user_profile_repository = user_profile_repository
        self._default_locale = default_locale

    async def execute(self, user_id: str | None = None, requested_locale: str | None = None) -> str:
        if requested_locale:
            return requested_locale
        if not user_id:
            return self._default_locale

        try:
            profile = await self._user_profile_repository.get(user_id)
        except Exception:  # noqa: BLE001 — see class docstring: never fail a turn over this
            logger.warning("Failed to read the profile for user %r", user_id, exc_info=True)
            return self._default_locale

        if profile is not None and profile.preferred_locale:
            return profile.preferred_locale
        return self._default_locale
