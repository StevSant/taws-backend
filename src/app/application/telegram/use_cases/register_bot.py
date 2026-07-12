import logging

from app.domain.telegram.entities import UserBot
from app.domain.telegram.ports import BotRegistrationPort

logger = logging.getLogger(__name__)


class RegisterBot:
    """Use case: register a user's own Telegram bot from BotFather text.

    Delegates to `BotRegistrationPort.register()` which handles:
    1. Parsing BotFather text → extract token + username
    2. Calling `getUpdates` → obtain chat_id
    3. Setting the webhook
    4. Persisting the bot registration
    """

    def __init__(self, registration: BotRegistrationPort) -> None:
        self._registration = registration

    async def execute(self, user_id: str, botfather_text: str) -> UserBot:
        return await self._registration.register(user_id, botfather_text)
