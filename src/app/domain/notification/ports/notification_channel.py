from abc import ABC, abstractmethod

from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.notification.entities import (
    Alert,
    BriefingReadyNotification,
    ScenarioMatchNotification,
)


class NotificationChannel(ABC):
    """Port for delivering a composed Watchdog notification to whatever channel is configured.

    Issue #10 ships exactly one adapter — `LoggingNotificationChannel`
    (`infrastructure/notification/logging_notification_channel.py`), a no-op/logging stand-in.
    Issue #14 implements `TelegramNotificationChannel` against this SAME port; nothing in
    `application/` or `api/` needs to change when that adapter lands — swap it in
    `core/di/container.py.Container.get_notification_channel()` only.

    Three notification shapes, each composed by a Watchdog use case and delivered the same
    "compose -> hand to port -> adapter resolves recipient -> delivers" way:

    - `send(Alert)` (issue #10) — a notification-worthy `Signal` surfaced by `RunWatchdogScan`.
    - `send_briefing_ready(BriefingReadyNotification)` (issue #16) — a scheduled Advisor
      `Briefing` finished generating, surfaced by `RunDailyBriefings`. A separate method
      rather than overloading `send(Alert)`: see `BriefingReadyNotification`'s docstring for
      why its shape doesn't fit `Alert`.
    - `send_scenario_match(ScenarioMatchNotification)` (issue #18) — an armed
      `ScenarioMonitor`'s scenario appears to be materializing, surfaced by
      `EvaluateScenarioMonitors`. Same "own shape, own method" reasoning as
      `send_briefing_ready` — see `ScenarioMatchNotification`'s docstring.
    """

    @abstractmethod
    async def send(self, alert: Alert) -> None:
        """Deliver one composed alert. Must not raise for expected delivery failures —
        adapters should log/swallow those so a bad delivery never crashes a scan."""
        raise NotImplementedError

    @abstractmethod
    async def send_briefing_ready(self, notification: BriefingReadyNotification) -> None:
        """Deliver one "briefing ready" notification. Same never-raise contract as `send`
        — adapters must log/swallow expected delivery failures so one watchlist's missing/
        broken recipient never breaks a scheduled daily briefing run for anyone else."""
        raise NotImplementedError

    @abstractmethod
    async def send_scenario_match(self, notification: ScenarioMatchNotification) -> None:
        """Deliver one "scenario materializing" match notification. Same never-raise
        contract as `send`/`send_briefing_ready` — one user's missing/broken Telegram link
        must never break Watchdog's scheduled monitor evaluation pass for anyone else."""
        raise NotImplementedError

    @abstractmethod
    async def broadcast_event_alert(self, event: EnrichedEvent) -> None:
        """Broadcast one important market event to EVERY linked recipient.

        The delivery half of the automatic Sentinel scan (`BroadcastImportantEvents`): a news
        event the Gemini analyzer judged important enough to interrupt people for. Same
        never-raise contract as the three above — one dead chat must not abort delivery to
        everyone behind it, and a broadcast failure must never kill the scheduled scan.

        **Broadcast, not addressed** — unlike `send`/`send_briefing_ready` (routed via a
        `watchlist_id`) and `send_scenario_match` (routed via a `user_id`), this one has no
        recipient on it at all: a market-moving event is not about one person's watchlist, so
        every user who linked their Telegram gets it. Resolving "everyone" stays inside the
        adapter, exactly like the other three resolve their own recipients.

        Takes the `EnrichedEvent` itself rather than a mirror notification entity: the adapter
        needs essentially every field on it (summary, affected assets/sectors, confidence, the
        suggested questions that become inline buttons), so a parallel entity would be a
        field-for-field copy with no added meaning. Both types are pure domain, so this stays
        a domain -> domain dependency with no vendor leak.
        """
        raise NotImplementedError
