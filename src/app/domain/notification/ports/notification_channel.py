from abc import ABC, abstractmethod

from app.domain.notification.entities import Alert


class NotificationChannel(ABC):
    """Port for delivering a composed Watchdog `Alert` to whatever channel is configured.

    Issue #10 ships exactly one adapter — `LoggingNotificationChannel`
    (`infrastructure/notification/logging_notification_channel.py`), a no-op/logging stand-in.
    Issue #14 implements `TelegramNotificationChannel` against this SAME port; nothing in
    `application/` or `api/` needs to change when that adapter lands — swap it in
    `core/di/container.py.Container.get_notification_channel()` only.
    """

    @abstractmethod
    async def send(self, alert: Alert) -> None:
        """Deliver one composed alert. Must not raise for expected delivery failures —
        adapters should log/swallow those so a bad delivery never crashes a scan."""
        raise NotImplementedError
