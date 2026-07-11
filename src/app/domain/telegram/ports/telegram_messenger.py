from abc import ABC, abstractmethod


class TelegramMessenger(ABC):
    """Port for sending a plain text message to one Telegram chat.

    Deliberately narrower than `NotificationChannel` (`domain/notification/ports`):
    this is the low-level "send text to a chat_id" primitive, shared by
    `TelegramNotificationChannel` (delivers Watchdog alerts) and `LinkTelegramAccount`
    (sends the "Linked!" confirmation after a successful `/start <token>`) so both flows
    reuse the same Telegram Bot API client without either depending on the other's
    higher-level shape.
    """

    @abstractmethod
    async def send_text(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> None:
        """Send `text` to `chat_id`. May raise on delivery failure — callers with a
        no-crash requirement (e.g. `NotificationChannel.send`) are responsible for
        catching and logging, same as any other port call.

        `parse_mode` optionally selects Telegram's `sendMessage` formatting mode (e.g.
        `"HTML"`, per https://core.telegram.org/bots/api#formatting-options) — `None`
        (the default) sends plain, unformatted text, preserving every existing caller's
        behavior. Introduced for issue #19's Telegram command replies (bold tickers,
        etc.); callers passing a non-`None` value are responsible for producing text
        that's already valid for that mode (e.g. HTML-escaped).
        """
        raise NotImplementedError
