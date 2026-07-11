from abc import ABC, abstractmethod

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
