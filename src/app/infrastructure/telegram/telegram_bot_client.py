from telegram import Bot

from app.domain.telegram.ports import TelegramMessenger


class TelegramBotClient(TelegramMessenger):
    """`TelegramMessenger` adapter backed by the Telegram Bot API, via `python-telegram-bot`.

    The ONLY place in this codebase allowed to import `telegram` (see `CLAUDE.md`'s
    hexagonal rule — vendor SDKs stay out of `domain/`/`application/`). Wraps a single
    `telegram.Bot` instance, cached process-wide by `Container.get_telegram_messenger()`.

    Deliberately thin: raises on failure instead of swallowing, so each caller (
    `TelegramNotificationChannel.send`, `LinkTelegramAccount._try_send`) applies its own
    no-crash policy rather than this client silently hiding delivery failures from both.
    """

    def __init__(self, bot_token: str) -> None:
        self._bot = Bot(token=bot_token)

    async def send_text(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> None:
        await self._bot.send_message(chat_id=int(chat_id), text=text, parse_mode=parse_mode)
