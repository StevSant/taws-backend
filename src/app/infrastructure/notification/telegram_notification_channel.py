import logging

from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
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

    That "never raises" contract covers the WHOLE method, not just the final Telegram API
    call: the two DB lookups above it (`WatchlistRepository.get`, then
    `TelegramLinkRepository.get_by_user_id`) can themselves raise on a transient
    Supabase/network error, and `RunWatchdogScan._scan_watchlist` (the only caller) has no
    try/except of its own around `send()` — an uncaught lookup error there would abort the
    entire scan loop, not just skip the one alert that failed, silently starving every
    other watchlist in that scan cycle of alert evaluation. So the whole body below runs
    under a single try/except, keeping this adapter self-contained: any future
    `NotificationChannel` implementation (email, Slack, ...) only has to honor the same
    "never raises" contract, not also audit every caller for missing guards.
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
        try:
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

            await self._messenger.send_text(link.chat_id, _format_alert(alert))
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            # Broad on purpose: a watchlist/link lookup failure and a Telegram API failure
            # are both just "this one alert didn't get delivered" from the scan loop's
            # point of view, and both must be equally non-fatal to it.
            logger.exception(
                "Failed to deliver Telegram alert %s for watchlist %s",
                alert.id,
                alert.watchlist_id,
            )


def _format_alert(alert: Alert) -> str:
    return (
        f"TAWS Alert — {alert.instrument_symbol}\n\n"
        f"{alert.consequence_hint}\n\n"
        f"View details: {alert.link_url}\n\n"
        f"{NOT_PERSONALIZED_ADVICE_DISCLAIMER}"
    )
