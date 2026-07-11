import logging

from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioMatchNotification,
)
from app.domain.notification.ports import NotificationChannel
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.domain.watchlist.ports import WatchlistRepository

logger = logging.getLogger(__name__)


class TelegramNotificationChannel(NotificationChannel):
    """Real `NotificationChannel` adapter (issue #14): resolves a Watchdog-composed
    notification to its recipient and delivers it over Telegram.

    Both `Alert` and `BriefingReadyNotification` only carry `watchlist_id` (see their
    docstrings) — resolving that to a real recipient is the same three-hop chain either
    way: `watchlist_id` -> `WatchlistRepository.get` -> owning `user_id` ->
    `TelegramLinkRepository.get_by_user_id` -> linked `chat_id`. That resolution happens
    HERE, inside the adapter (`_resolve_chat_id`, shared by both `send` and
    `send_briefing_ready`), rather than by changing the `NotificationChannel` port or
    either entity — "how to route a notification to a real recipient" is squarely a
    delivery-adapter concern, and keeping both entities' shapes unchanged means any future
    channel (email, Slack, ...) can resolve recipients however fits it best.

    Missing-link fallback: if the watchlist's owner can't be resolved, or has no linked
    Telegram chat, or the Telegram API call itself fails, both `send()` and
    `send_briefing_ready()` log and return — never raise. Same graceful-degradation spirit
    as `LoggingNotificationChannel`, so one user's missing/broken link never breaks
    Watchdog's scan loop or the daily briefing run for anyone else.

    That "never raises" contract covers the WHOLE method, not just the final Telegram API
    call: the two DB lookups above it (`WatchlistRepository.get`, then
    `TelegramLinkRepository.get_by_user_id`) can themselves raise on a transient
    Supabase/network error, and neither caller (`RunWatchdogScan._scan_watchlist`,
    `RunDailyBriefings.execute`) wraps its own try/except around these calls — an uncaught
    lookup error here would abort the entire scan/briefing loop, not just skip the one
    notification that failed, silently starving every other watchlist in that cycle. So
    the whole body of each `send*` method runs under a single try/except, keeping this
    adapter self-contained: any future `NotificationChannel` implementation (email,
    Slack, ...) only has to honor the same "never raises" contract, not also audit every
    caller for missing guards.
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
            chat_id = await self._resolve_chat_id(alert.watchlist_id, context=f"alert {alert.id}")
            if chat_id is None:
                return
            await self._messenger.send_text(chat_id, _format_alert(alert))
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            # Broad on purpose: a watchlist/link lookup failure and a Telegram API failure
            # are both just "this one alert didn't get delivered" from the scan loop's
            # point of view, and both must be equally non-fatal to it.
            logger.exception(
                "Failed to deliver Telegram alert %s for watchlist %s",
                alert.id,
                alert.watchlist_id,
            )

    async def send_briefing_ready(self, notification: BriefingReadyNotification) -> None:
        try:
            chat_id = await self._resolve_chat_id(
                notification.watchlist_id, context=f"briefing {notification.briefing_id}"
            )
            if chat_id is None:
                return
            await self._messenger.send_text(chat_id, _format_briefing_ready(notification))
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            logger.exception(
                "Failed to deliver Telegram briefing-ready notification %s for watchlist %s",
                notification.briefing_id,
                notification.watchlist_id,
            )

    async def send_scenario_match(self, notification: ScenarioMatchNotification) -> None:
        try:
            chat_id = await self._resolve_chat_id_for_user(
                notification.user_id, context=f"scenario match {notification.monitor_id}"
            )
            if chat_id is None:
                return
            await self._messenger.send_text(chat_id, _format_scenario_match(notification))
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            logger.exception(
                "Failed to deliver Telegram scenario-match notification %s for user %s",
                notification.monitor_id,
                notification.user_id,
            )

    async def _resolve_chat_id_for_user(self, user_id: str, *, context: str) -> str | None:
        """Resolve a `user_id` directly to its linked Telegram `chat_id`, or `None` if the
        user has no linked chat. Used only by `send_scenario_match`, which — unlike
        `send`/`send_briefing_ready` — has a `user_id` in hand already and doesn't need the
        `watchlist_id` -> owning-`user_id` hop `_resolve_chat_id` performs (see
        `ScenarioMatchNotification`'s docstring). Deliberately does NOT catch exceptions
        itself — same "caller wraps its own try/except" contract as `_resolve_chat_id`.
        """
        link = await self._telegram_link_repository.get_by_user_id(user_id)
        if link is None:
            logger.info(
                "user %s has no linked Telegram chat; skipping delivery for %s", user_id, context
            )
            return None
        return link.chat_id

    async def _resolve_chat_id(self, watchlist_id: str, *, context: str) -> str | None:
        """Resolve a `watchlist_id` to its owner's linked Telegram `chat_id`, or `None` if
        the watchlist is unknown or its owner has no linked chat. Shared by `send` and
        `send_briefing_ready` — see class docstring for why this lives here rather than
        being duplicated per notification kind. Deliberately does NOT catch exceptions
        itself: both callers wrap their own single try/except around this, per the class
        docstring's "never raises" contract.
        """
        watchlist = await self._watchlist_repository.get(watchlist_id)
        if watchlist is None:
            logger.warning(
                "%s references unknown watchlist %s; skipping Telegram delivery",
                context,
                watchlist_id,
            )
            return None

        link = await self._telegram_link_repository.get_by_user_id(watchlist.user_id)
        if link is None:
            logger.info(
                "user %s has no linked Telegram chat; skipping delivery for %s",
                watchlist.user_id,
                context,
            )
            return None

        return link.chat_id


def _format_alert(alert: Alert) -> str:
    return (
        f"TAWS Alert — {alert.instrument_symbol}\n\n"
        f"{alert.consequence_hint}\n\n"
        f"View details: {alert.link_url}\n\n"
        f"{NOT_PERSONALIZED_ADVICE_DISCLAIMER}"
    )


def _format_briefing_ready(notification: BriefingReadyNotification) -> str:
    return (
        "TAWS Briefing Ready\n\n"
        f"{notification.headline}\n\n"
        f"View briefing: {notification.link_url}\n\n"
        f"{NOT_PERSONALIZED_ADVICE_DISCLAIMER}"
    )


def _format_scenario_match(notification: ScenarioMatchNotification) -> str:
    return (
        f"TAWS Scenario Watch — {notification.scenario_title}\n\n"
        f"{notification.match_reason}\n\n"
        f"View scenario: {notification.link_url}\n\n"
        f"{NOT_PERSONALIZED_ADVICE_DISCLAIMER}"
    )
