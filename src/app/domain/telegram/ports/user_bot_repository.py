from abc import ABC, abstractmethod

from app.domain.telegram.entities import UserBot


class UserBotRepository(ABC):
    """Port for persisting and retrieving per-user Telegram bot registrations.

    Each user can register at most one bot (enforced by the `unique (user_id)`
    constraint in the `user_bots` table — see migration 0009).
    """

    @abstractmethod
    async def get_by_user_id(self, user_id: str) -> UserBot | None:
        ...

    @abstractmethod
    async def get_by_id(self, bot_id: str) -> UserBot | None:
        ...

    @abstractmethod
    async def get_by_chat_id(self, chat_id: str) -> list[UserBot]:
        ...

    @abstractmethod
    async def get_all(self) -> list[UserBot]:
        ...

    @abstractmethod
    async def save(self, bot: UserBot) -> UserBot:
        ...

    @abstractmethod
    async def delete(self, user_id: str) -> None:
        ...
