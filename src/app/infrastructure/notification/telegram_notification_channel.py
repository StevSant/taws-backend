import logging
from collections.abc import Mapping, Sequence

from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER, disclaimer_for_locale
from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioArmedNotification,
    ScenarioMatchNotification,
)
from app.domain.notification.ports import NotificationChannel
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.telegram import (
    build_event_alert_buttons,
    format_event_alert,
    format_personalized_event_alert,
)

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
        frontend_base_url: str,
    ) -> None:
        self._messenger = messenger
        self._watchlist_repository = watchlist_repository
        self._telegram_link_repository = telegram_link_repository
        self._frontend_base_url = frontend_base_url

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

    async def send_scenario_armed(self, notification: ScenarioArmedNotification) -> None:
        try:
            chat_id = await self._resolve_chat_id_for_user(
                notification.user_id, context=f"scenario armed {notification.monitor_id}"
            )
            if chat_id is None:
                return
            await self._messenger.send_text(chat_id, _format_scenario_armed(notification))
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            logger.exception(
                "Failed to deliver Telegram scenario-armed confirmation %s for user %s",
                notification.monitor_id,
                notification.user_id,
            )

    async def broadcast_event_alert(self, event: EnrichedEvent) -> None:
        """Fan one important market event out to EVERY linked chat, with inline buttons.

        Per-recipient isolation is the whole point of the inner try/except: one dead chat (bot
        blocked, account deleted, chat cleared) must not abort delivery to everyone queued
        behind it — which is exactly what a single try around the loop would do. The outer
        guard covers the `list_all()` lookup itself, keeping this method's never-raise contract
        whole so a scheduled Sentinel scan can't be killed by a transient Supabase blip.
        """
        try:
            links = await self._telegram_link_repository.list_all()
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            logger.exception("Failed to list Telegram links for event %s", event.id)
            return

        if not links:
            logger.info("No linked Telegram chats; event %s not broadcast", event.id)
            return

        text = format_event_alert(event)
        buttons = build_event_alert_buttons(event, self._frontend_base_url)
        delivered = 0
        for link in links:
            try:
                await self._messenger.send_text(
                    link.chat_id, text, parse_mode="HTML", buttons=buttons
                )
                delivered += 1
            except Exception:  # noqa: BLE001 — one bad chat must not stop the rest
                logger.exception("Failed to broadcast event %s to chat %s", event.id, link.chat_id)
        logger.info("event %s broadcast to %d/%d linked chat(s)", event.id, delivered, len(links))

    async def send_event_alert_to_user(
        self,
        event: EnrichedEvent,
        user_id: str,
        watched_symbols: Sequence[str],
        asset_impacts: Mapping[str, str],
    ) -> None:
        """Deliver one important market event to a single user's linked chat, PERSONALIZED.

        Same inline buttons as `broadcast_event_alert`, addressed to one recipient — the
        watchlist-targeted delivery path for a mid-importance event — but the body is rendered by
        `format_personalized_event_alert`, which appends a "why this matters to you" section built
        from `watched_symbols` (the event's affected assets this user tracks) and the shared
        `asset_impacts` map. Reuses the existing `_resolve_chat_id_for_user` hop (user_id ->
        linked chat_id). Never raises: a missing link is a no-op, and a lookup/send failure logs
        and returns, so `BroadcastImportantEvents`' per-user delivery loop can't be aborted by one
        bad recipient (mirrors the per-recipient isolation of the broadcast loop above).
        """
        try:
            chat_id = await self._resolve_chat_id_for_user(user_id, context=f"event {event.id}")
            if chat_id is None:
                return
            await self._messenger.send_text(
                chat_id,
                format_personalized_event_alert(event, watched_symbols, asset_impacts),
                parse_mode="HTML",
                buttons=build_event_alert_buttons(event, self._frontend_base_url),
            )
        except Exception:  # noqa: BLE001 — this port must never raise; see class docstring.
            logger.exception("Failed to deliver Telegram event %s to user %s", event.id, user_id)

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


# Chrome around the alert body, per language. `consequence_hint` already arrives written in
# `alert.locale` (see `derive_consequence_hint`); these are the remaining strings that used to be
# unconditionally English, which is what produced a Spanish-UI user receiving an entirely English
# Telegram alert. Keyed by primary language subtag so `es-MX` resolves to Spanish.
_ALERT_CHROME = {
    "es": {"header": "Alerta TAWS", "link_label": "Ver detalles"},
    "en": {"header": "TAWS Alert", "link_label": "View details"},
}


def _format_alert(alert: Alert) -> str:
    language = alert.locale.split("-", 1)[0].strip().lower()
    chrome = _ALERT_CHROME.get(language, _ALERT_CHROME["en"])
    return (
        f"{chrome['header']} — {alert.instrument_symbol}\n\n"
        f"{alert.consequence_hint}\n\n"
        f"{chrome['link_label']}: {alert.link_url}\n\n"
        f"{disclaimer_for_locale(alert.locale)}"
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


# Localized chrome for the arm confirmation. Keyed by primary language subtag so `es-MX`
# resolves to Spanish; this is user-facing copy, so it follows the scenario's own locale
# rather than being hardcoded English like the (pre-locale) formatters above.
_SCENARIO_ARMED_CHROME = {
    "es": {
        "header": "Vigilancia activada",
        "body": "Vigilaré este escenario y te avisaré si empieza a materializarse.",
        "expires_label": "Vence",
        "link_label": "Ver escenario",
    },
    "en": {
        "header": "Monitoring activated",
        "body": "I'll watch this scenario and alert you if it starts to materialize.",
        "expires_label": "Expires",
        "link_label": "View scenario",
    },
}


def _format_scenario_armed(notification: ScenarioArmedNotification) -> str:
    language = notification.locale.split("-", 1)[0].strip().lower()
    chrome = _SCENARIO_ARMED_CHROME.get(language, _SCENARIO_ARMED_CHROME["en"])
    return (
        f"{chrome['header']} — {notification.scenario_title}\n\n"
        f"{chrome['body']}\n\n"
        f"{chrome['expires_label']}: {notification.expires_at:%Y-%m-%d}\n\n"
        f"{chrome['link_label']}: {notification.link_url}\n\n"
        f"{disclaimer_for_locale(notification.locale)}"
    )
