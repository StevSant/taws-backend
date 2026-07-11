import logging

from app.domain.compliance.disclaimer import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.notification.entities import Alert
from app.domain.notification.ports import NotificationChannel
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.domain.watchlist.ports import WatchlistRepository

logger = logging.getLogger(__name__)


class TelegramNotificationChannel(NotificationChannel):
    """Real `NotificationChannel` adapter (issue #14): resolves a Watchdog-composed
    `Alert` to its recipient and delivers it over Telegram.

    `Alert` only carries `watchlist_id` (see `domain/notification/entities/alert.py`) —
    resolving that to a real recipient is a three-hop chain: `watchlist_id` ->
    `WatchlistRepository.get` -> owning `user_id` -> `TelegramLinkRepository.get_by_user_id`
    -> linked `chat_id`. That resolution happens HERE, inside the adapter, rather than by
    changing the `NotificationChannel` port or `Alert` entity — `Alert` already carries
    everything `RunWatchdogScan` (issue #10) produces, "how to route an alert to a real
    recipient" is squarely a delivery-adapter concern, and keeping the port shape
    unchanged means any future channel (email, Slack, ...) can resolve recipients however
    fits it best without a shared, growing `Alert` payload.

    Missing-link fallback: if the watchlist's owner can't be resolved, or has no linked
    Telegram chat, or the Telegram API call itself fails, `send()` logs and returns —
    never raises. Same graceful-degradation spirit as `LoggingNotificationChannel`, so one
    user's missing/broken link never breaks Watchdog's scan loop for anyone else.
    """

    def __init__(
        self,
        messenger: TelegramMessenger,
        watchlist_repository: WatchlistRepository,
        telegram_link_repository: TelegramLinkRepository,
    ) -> None:
        self._messenger = messenger
        self._watchlist_repository = watchlist_repository
        self._telegram_link_repository = telegram_link_repository

    async def send(self, alert: Alert) -> None:
        watchlist = await self._watchlist_repository.get(alert.watchlist_id)
        if watchlist is None:
            logger.warning(
                "alert %s references unknown watchlist %s; skipping Telegram delivery",
                alert.id,
                alert.watchlist_id,
            )
            return

        link = await self._telegram_link_repository.get_by_user_id(watchlist.user_id)
        if link is None:
            logger.info(
                "user %s has no linked Telegram chat; skipping delivery for alert %s",
                watchlist.user_id,
                alert.id,
            )
            return

        try:
            await self._messenger.send_text(link.chat_id, _format_alert(alert))
        except Exception:  # noqa: BLE001 — a bad delivery must never crash the scan loop
            logger.exception(
                "Failed to deliver Telegram alert %s to chat_id=%s", alert.id, link.chat_id
            )


def _format_alert(alert: Alert) -> str:
    return (
        f"TAWS Alert — {alert.instrument_symbol}\n\n"
        f"{alert.consequence_hint}\n\n"
        f"View details: {alert.link_url}\n\n"
        f"{NOT_PERSONALIZED_ADVICE_DISCLAIMER}"
    )
