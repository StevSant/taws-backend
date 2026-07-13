from abc import ABC, abstractmethod

from app.domain.profile.entities import UserProfile


class UserProfileRepository(ABC):
    """Port for reading/writing a user's stored preferences (issue #67)."""

    @abstractmethod
    async def get(self, user_id: str) -> UserProfile | None:
        """Return the profile for `user_id`, or `None` when no row exists yet."""
        raise NotImplementedError

    @abstractmethod
    async def set_preferred_locale(self, user_id: str, preferred_locale: str | None) -> UserProfile:
        """Upsert `user_id`'s preferred locale and return the profile as persisted.

        Upsert, not update: the row is created lazily the first time a user expresses a
        preference, so signup doesn't have to write a profile nobody has customized yet.
        `None` clears the preference (back to `Settings.default_locale`).
        """
        raise NotImplementedError
