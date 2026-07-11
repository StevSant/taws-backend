from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class BriefingReadyNotification:
    """A Watchdog/Notifier-agent-composed notification that a scheduled Advisor `Briefing`
    has finished generating for one watchlist (issue #16).

    Produced by `RunDailyBriefings` (`application/watchdog/use_cases/run_daily_briefings.py`)
    and handed to a `NotificationChannel` port adapter for delivery — the exact same
    "compose -> hand to port -> adapter resolves recipient -> delivers" pattern `Alert`
    uses for Watchdog's signal alerting (`run_watchdog_scan.py`).

    Kept as its own entity rather than reusing `Alert`: `Alert.signal_id`/
    `Alert.instrument_symbol` are both required, single-value fields, and a briefing is
    about a whole watchlist (many linked signals, many instruments) — there is no single
    signal or instrument to put there. Extending `Alert` with nullable signal/instrument
    fields "for the briefing case" would make every `Alert` consumer (the API's
    `AlertResponse` schema, `LoggingNotificationChannel`, `TelegramNotificationChannel`'s
    formatter) branch on which kind of alert it received; a second, narrowly-shaped entity
    plus a second `NotificationChannel` method is the smaller, clearer change.
    """

    id: str
    briefing_id: str
    watchlist_id: str
    headline: str
    link_url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
