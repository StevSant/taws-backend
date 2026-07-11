import logging

from app.domain.notification.entities import Alert
from app.domain.notification.ports import NotificationChannel

logger = logging.getLogger(__name__)


class LoggingNotificationChannel(NotificationChannel):
    """No-op `NotificationChannel` adapter: logs the composed alert instead of delivering it.

    Stand-in until issue #14 ships `TelegramNotificationChannel` against the same port. Keeps
    Watchdog demo-able end to end (scan -> decide -> compose -> "deliver") without hard-depending
    on a parallel issue's Telegram integration.
    """

    async def send(self, alert: Alert) -> None:
        logger.info(
            "watchdog alert composed: instrument=%s signal=%s watchlist=%s hint=%r link=%s",
            alert.instrument_symbol,
            alert.signal_id,
            alert.watchlist_id,
            alert.consequence_hint,
            alert.link_url,
        )
