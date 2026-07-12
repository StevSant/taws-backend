import logging

import httpx

from app.domain.telegram.entities import UserBot
from app.domain.telegram.ports import BotRegistrationPort, UserBotRepository
from app.infrastructure.telegram.botfather_parser import parse_botfather_text

logger = logging.getLogger(__name__)



class TelegramBotRegistration(BotRegistrationPort):
    """`BotRegistrationPort` adapter: parses BotFather text, calls `getUpdates` to
    obtain the user's `chat_id`, sets the webhook, and persists via `UserBotRepository`.

    Flow:
    1. Parse BotFather text → extract `bot_token` and `bot_username`
    2. Call `getUpdates` → extract `chat_id` from the first message
    3. Set webhook for the bot
    4. Save to repository
    """

    def __init__(
        self,
        repository: UserBotRepository,
        webhook_base_url: str,
    ) -> None:
        self._repository = repository
        self._webhook_base_url = webhook_base_url

    async def register(self, user_id: str, botfather_text: str) -> UserBot:

        parsed = parse_botfather_text(botfather_text)
        if parsed is None:
            raise ValueError(
                "No se pudo extraer el token y username del texto de BotFather. "
                "Asegúrate de pegar el mensaje completo que te envió BotFather."
            )

        chat_id = await self._get_chat_id(parsed.bot_token)
        if chat_id is None:
            raise ValueError(
                "No se encontró ningún mensaje en el bot. "
                f"Envía cualquier mensaje a @{parsed.bot_username} y vuelve a intentarlo."
            )

        bot = UserBot(
            id="",
            user_id=user_id,
            bot_token=parsed.bot_token,
            bot_username=parsed.bot_username,
            chat_id=chat_id,
        )
        saved = await self._repository.save(bot)

        await self._set_webhook(parsed.bot_token, saved.id)

        return saved

    async def _get_chat_id(self, bot_token: str) -> str | None:
        """Call `getUpdates` to find the user's chat_id.

        The user must have sent at least one message to the bot before calling this.
        Returns the `chat_id` from the first message, or `None` if no messages exist.
        """
        await self._delete_webhook(bot_token)
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("Failed to call getUpdates for bot token %s", bot_token[:8])
            return None

        if not data.get("ok") or not data.get("result"):
            return None

        for update in data["result"]:
            message = (
                update.get("message")
                or update.get("edited_message")
                or update.get("channel_post")
            )
            if message and "chat" in message:
                chat_id = message["chat"].get("id")
                if chat_id is not None:
                    return str(chat_id)

        return None

    async def _delete_webhook(self, bot_token: str) -> None:
        """Delete any existing webhook for this bot so `getUpdates` can be used."""
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
        except Exception:
            logger.exception("Failed to delete webhook for bot token %s", bot_token[:8])

    async def _set_webhook(self, bot_token: str, bot_id: str) -> None:
        """Set the Telegram webhook for this bot.

        The webhook URL is `{webhook_base_url}/api/v1/telegram/webhook/{bot_id}`.
        """
        webhook_url = f"{self._webhook_base_url.rstrip('/')}/{bot_id}"
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json={"url": webhook_url}, timeout=10)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    logger.warning(
                        "Telegram setWebhook returned not-ok for bot %s: %s",
                        bot_id,
                        data,
                    )
        except Exception:
            logger.exception("Failed to set webhook for bot %s", bot_id)
