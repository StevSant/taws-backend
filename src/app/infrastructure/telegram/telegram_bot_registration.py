import logging

import httpx

from app.domain.telegram.entities import UserBot
from app.domain.telegram.ports import BotRegistrationPort, UserBotRepository
from app.infrastructure.telegram.botfather_parser import parse_botfather_text

logger = logging.getLogger(__name__)


class TelegramBotRegistration(BotRegistrationPort):
    """`BotRegistrationPort` adapter: parses BotFather text, resolves the user's `chat_id`,
    sets the webhook, and persists via `UserBotRepository`.

    Flow:
    1. Parse BotFather text → extract `bot_token` and `bot_username`
    2. Resolve `chat_id` — reuse the stored one when re-registering the same bot, otherwise
       call `getUpdates` and read it off the first message
    3. Set webhook for the bot
    4. Save to repository

    Step 2 must prefer the stored `chat_id`: `setWebhook` (step 3) makes Telegram deliver
    every pending update to the webhook, which drains the `getUpdates` queue. So once a bot
    is registered, `getUpdates` is empty forever, and re-deriving `chat_id` from it would
    always fail — even though we already know the answer. Registration is idempotent: the
    same BotFather text can be submitted twice.
    """

    def __init__(
        self,
        repository: UserBotRepository,
        webhook_base_url: str,
        webhook_secret: str | None = None,
    ) -> None:
        self._repository = repository
        self._webhook_base_url = webhook_base_url
        self._webhook_secret = webhook_secret

    async def register(self, user_id: str, botfather_text: str) -> UserBot:

        parsed = parse_botfather_text(botfather_text)
        if parsed is None:
            raise ValueError(
                "No se pudo extraer el token y username del texto de BotFather. "
                "Asegúrate de pegar el mensaje completo que te envió BotFather."
            )

        existing = await self._repository.get_by_user_id(user_id)
        chat_id = await self._resolve_chat_id(existing, parsed.bot_token)
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

        try:
            await self._set_webhook(parsed.bot_token, saved.id)
        except Exception:
            # Roll the insert back only when we created it. `save` upserts on `user_id`, so
            # for a re-registration this row predates the call — deleting it would let a
            # failed retry destroy a registration that was working a moment ago.
            if existing is None:
                await self._repository.delete(user_id)
            raise

        return saved

    async def _resolve_chat_id(self, existing: UserBot | None, bot_token: str) -> str | None:
        """The `chat_id` for `bot_token`, reusing `existing`'s when it's the same bot.

        Re-registering a bot the user already registered (a second "Registrar Bot" click, or
        a retry after a failure) must NOT ask Telegram again: this bot's webhook has already
        consumed the message `getUpdates` would have read, so Telegram would answer "no
        messages" and we'd reject a perfectly valid registration. `user_bots.chat_id` is
        `not null`, so a stored row always carries a usable `chat_id`.

        Only a bot we've never seen for this user falls through to `getUpdates` — and only
        that path deletes the webhook, so a retry can no longer knock a working bot offline.
        """
        if existing is not None and existing.bot_token == bot_token and existing.chat_id:
            logger.info("Reusing stored chat_id for already-registered bot %s", existing.id)
            return existing.chat_id
        return await self._get_chat_id(bot_token)

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
                update.get("message") or update.get("edited_message") or update.get("channel_post")
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
        Raises `ValueError` if the webhook cannot be set, so the registration
        endpoint can surface the error to the user instead of silently continuing.
        """
        webhook_url = f"{self._webhook_base_url.rstrip('/')}/{bot_id}"
        if not webhook_url.startswith("http"):
            raise ValueError(
                f"Webhook URL '{webhook_url}' no es válida. "
                "Revisa que TELEGRAM_WEBHOOK_URL esté configurada en .env "
                "y que el servidor se haya reiniciado tras el cambio."
            )
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        body = {"url": webhook_url}
        if self._webhook_secret:
            body["secret_token"] = self._webhook_secret
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=body, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise ValueError(
                    f"Telegram rechazó el webhook: {data.get('description', 'error desconocido')}"
                )
