from abc import ABC, abstractmethod

from app.domain.telegram.entities import UserBot


class BotRegistrationPort(ABC):
    """Port for registering a user's own Telegram bot.

    Orchestrates: parse BotFather text → get chat_id via getUpdates → set webhook → persist.
    """

    @abstractmethod
    async def register(self, user_id: str, botfather_text: str) -> UserBot: ...
