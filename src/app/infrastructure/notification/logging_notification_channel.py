import logging

from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioArmedNotification,
    ScenarioMatchNotification,
)
from app.domain.notification.ports import NotificationChannel

logger = logging.getLogger(__name__)


class LoggingNotificationChannel(NotificationChannel):
    """No-op `NotificationChannel` adapter: logs the composed notification instead of
    delivering it.

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

    async def send_briefing_ready(self, notification: BriefingReadyNotification) -> None:
        logger.info(
            "briefing ready notification composed: briefing=%s watchlist=%s headline=%r link=%s",
            notification.briefing_id,
            notification.watchlist_id,
            notification.headline,
            notification.link_url,
        )

    async def send_scenario_match(self, notification: ScenarioMatchNotification) -> None:
        logger.info(
            "scenario match notification composed: monitor=%s scenario=%s user=%s "
            "reason=%r link=%s",
            notification.monitor_id,
            notification.scenario_id,
            notification.user_id,
            notification.match_reason,
            notification.link_url,
        )

    async def send_scenario_armed(self, notification: ScenarioArmedNotification) -> None:
        logger.info(
            "scenario armed confirmation composed: monitor=%s scenario=%s user=%s title=%r "
            "expires=%s link=%s",
            notification.monitor_id,
            notification.scenario_id,
            notification.user_id,
            notification.scenario_title,
            notification.expires_at.isoformat(),
            notification.link_url,
        )

    async def broadcast_event_alert(self, event: EnrichedEvent) -> None:
        logger.info(
            "important event alert composed: event=%s importance=%.2f confidence=%.2f "
            "title=%r assets=%s sectors=%s",
            event.id,
            event.importance,
            event.confidence,
            event.original.title,
            event.affected_assets,
            event.affected_sectors,
        )
