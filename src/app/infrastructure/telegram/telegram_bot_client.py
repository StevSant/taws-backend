from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from app.domain.telegram.entities import InlineButton
from app.domain.telegram.ports import TelegramMessenger


class TelegramBotClient(TelegramMessenger):
    """`TelegramMessenger` adapter backed by the Telegram Bot API, via `python-telegram-bot`.

    The ONLY place in this codebase allowed to import `telegram` (see `CLAUDE.md`'s
    hexagonal rule — vendor SDKs stay out of `domain/`/`application/`). Wraps a single
    `telegram.Bot` instance, cached process-wide by `Container.get_telegram_messenger()`.
    Mapping the domain's `InlineButton` onto `InlineKeyboardButton`/`InlineKeyboardMarkup`
    happens here too, so the vendor's keyboard types never leak upward either.

    Deliberately thin: raises on failure instead of swallowing, so each caller (
    `TelegramNotificationChannel.send`, `LinkTelegramAccount._try_send`) applies its own
    no-crash policy rather than this client silently hiding delivery failures from both.
    """

    def __init__(self, bot_token: str) -> None:
        self._bot = Bot(token=bot_token)

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str | None = None,
        buttons: list[list[InlineButton]] | None = None,
    ) -> None:
        await self._bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode=parse_mode,
            reply_markup=_to_markup(buttons),
        )

    async def send_photo(
        self,
        chat_id: str,
        image: bytes,
        caption: str | None = None,
        *,
        parse_mode: str | None = None,
    ) -> None:
        await self._bot.send_photo(
            chat_id=int(chat_id),
            photo=image,
            caption=caption,
            parse_mode=parse_mode,
        )

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> None:
        await self._bot.answer_callback_query(callback_query_id=callback_query_id, text=text)


def _to_markup(buttons: list[list[InlineButton]] | None) -> InlineKeyboardMarkup | None:
    """Map domain button rows onto the vendor keyboard, or `None` for no keyboard.

    Empty rows are dropped and an entirely empty keyboard maps to `None`, not an empty markup:
    Telegram rejects a `reply_markup` containing no buttons, and "the analyzer suggested no
    questions" is a perfectly ordinary way to end up with nothing to render.
    """
    if not buttons:
        return None
    rows = [
        [
            InlineKeyboardButton(
                text=button.text, url=button.url, callback_data=button.callback_data
            )
            for button in row
        ]
        for row in buttons
        if row
    ]
    return InlineKeyboardMarkup(rows) if rows else None
