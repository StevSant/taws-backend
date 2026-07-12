import logging

import logging

from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioMatchNotification,
)
from app.domain.notification.ports import NotificationChannel
from app.domain.telegram.ports import TelegramLinkRepository, UserBotRepository
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.telegram import TelegramBotClient

logger = logging.getLogger(__name__)


class MultiBotNotificationChannel(NotificationChannel):
    """Sends notifications to ALL registered user bots instead of a single main bot.

    When `TELEGRAM_BOT_TOKEN` is not configured, this adapter replaces the
    `TelegramNotificationChannel` by fanning out to every bot registered via
    `POST /api/v1/telegram/register-bot`. Each bot sends the notification to
    its own chat (the user's Telegram chat ID).
    """

    def __init__(
        self,
        user_bot_repository: "UserBotRepository",
        watchlist_repository: WatchlistRepository,
        telegram_link_repository: TelegramLinkRepository,
    ) -> None:
        self._user_bot_repository = user_bot_repository
        self._watchlist_repository = watchlist_repository
        self._telegram_link_repository = telegram_link_repository

    async def send(self, alert: Alert) -> None:
        try:
            chat_id = await self._resolve_chat_id(alert.watchlist_id, context=f"alert {alert.id}")
            if chat_id is None:
                return
            await self._send_to_all_bots(chat_id, _format_alert(alert))
        except Exception:
            logger.exception(
                "Failed to deliver multi-bot alert %s for watchlist %s",
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
            await self._send_to_all_bots(chat_id, _format_briefing_ready(notification))
        except Exception:
            logger.exception(
                "Failed to deliver multi-bot briefing-ready notification %s for watchlist %s",
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
            await self._send_to_all_bots(chat_id, _format_scenario_match(notification))
        except Exception:
            logger.exception(
                "Failed to deliver multi-bot scenario-match notification %s for user %s",
                notification.monitor_id,
                notification.user_id,
            )

    async def _send_to_all_bots(self, chat_id: str, text: str) -> None:
        bots = await self._user_bot_repository.get_by_chat_id(chat_id)
        if not bots:
            logger.info("No registered bots for chat_id %s; skipping notification", chat_id)
            return
        for bot in bots:
            try:
                client = TelegramBotClient(bot_token=bot.bot_token)
                await client.send_text(chat_id, text)
            except Exception:
                logger.exception(
                    "Failed to send notification via bot %s for chat_id %s",
                    bot.bot_username,
                    chat_id,
                )

    async def _resolve_chat_id_for_user(self, user_id: str, *, context: str) -> str | None:
        link = await self._telegram_link_repository.get_by_user_id(user_id)
        if link is None:
            logger.info(
                "user %s has no linked Telegram chat; skipping delivery for %s", user_id, context
            )
            return None
        return link.chat_id

    async def _resolve_chat_id(self, watchlist_id: str, *, context: str) -> str | None:
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