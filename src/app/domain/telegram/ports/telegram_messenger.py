from abc import ABC, abstractmethod

from app.domain.telegram.entities import InlineButton


class TelegramMessenger(ABC):
    """Port for sending a message to one Telegram chat.

    Deliberately narrower than `NotificationChannel` (`domain/notification/ports`):
    this is the low-level "send to a chat_id" primitive, shared by
    `TelegramNotificationChannel` (delivers Watchdog alerts) and `LinkTelegramAccount`
    (sends the "Linked!" confirmation after a successful `/start <token>`) so both flows
    reuse the same Telegram Bot API client without either depending on the other's
    higher-level shape.
    """

    @abstractmethod
    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        parse_mode: str | None = None,
        buttons: list[list[InlineButton]] | None = None,
    ) -> None:
        """Send `text` to `chat_id`. May raise on delivery failure — callers with a
        no-crash requirement (e.g. `NotificationChannel.send`) are responsible for
        catching and logging, same as any other port call.

        `parse_mode` optionally selects Telegram's `sendMessage` formatting mode (e.g.
        `"HTML"`, per https://core.telegram.org/bots/api#formatting-options) — `None`
        (the default) sends plain, unformatted text, preserving every existing caller's
        behavior. Callers passing a non-`None` value are responsible for producing text
        that's already valid for that mode (e.g. HTML-escaped).

        `buttons` attaches an inline keyboard — a list of ROWS, each a list of buttons, which
        is how Telegram lays them out. `None` (the default) sends no keyboard, so every
        existing caller is unaffected. Added for the automatic news alerts, whose messages
        carry "Ver en TAWS" / "Preguntar a Midas" / "Analizar impacto" actions; before this the
        port could only ever send inert text.
        """
        raise NotImplementedError

    @abstractmethod
    async def send_photo(
        self,
        chat_id: str,
        image: bytes,
        caption: str | None = None,
        *,
        parse_mode: str | None = None,
    ) -> None:
        """Send a PNG `image` to `chat_id` with an optional `caption` (`sendPhoto`).

        Added for server-side chart images (issue #1): the Telegram chat handler renders a
        `ChartSpec` to PNG bytes and delivers it here. Telegram caps a photo caption at 1024
        characters, so callers must truncate `caption` before calling (see
        `truncate_telegram_caption`). Like `send_text`, this MAY raise on delivery failure —
        callers with a no-crash requirement catch and log, so one failed chart never breaks
        the text reply that already went out.
        """
        raise NotImplementedError

    @abstractmethod
    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> None:
        """Acknowledge a tapped inline button (`answerCallbackQuery`).

        Telegram spins the button until this is called and re-delivers the update if it never
        is, so this must fire for EVERY `callback_query` — including ones we choose to ignore,
        and including ones whose handling failed. `text`, when given, surfaces as a small toast
        in the client; it's the right place for "that news item expired", which is a normal
        outcome here since enriched events live in an in-memory store a restart clears.
        """
        raise NotImplementedError
