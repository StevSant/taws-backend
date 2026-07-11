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
    async def send_text(self, chat_id: str, text: str) -> None:
        """Send `text` to `chat_id`. May raise on delivery failure — callers with a
        no-crash requirement (e.g. `NotificationChannel.send`) are responsible for
        catching and logging, same as any other port call."""
        raise NotImplementedError
