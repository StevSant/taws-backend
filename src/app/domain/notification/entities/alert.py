from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Alert:
    """A Watchdog/Notifier-agent-composed notification for one notification-worthy `Signal`.

    Produced by `RunWatchdogScan` (`application/watchdog/use_cases/run_watchdog_scan.py`) and
    handed to a `NotificationChannel` port adapter for delivery. Informational only — an alert
    surfaces an already-persisted `Signal`, it is never a trading/execution instruction.

    `consequence_hint` is a short, plain-language string derived from the signal's own
    evidence (see `_derive_consequence_hint` in `run_watchdog_scan.py`) — NOT a call to the
    Consequence Chain agent (issue #8, optional/nice-to-have, not hard-depended on here).
    `link_url` points back to the app (config-driven base URL, `Settings.frontend_base_url`),
    never a hardcoded frontend URL.
    """

    id: str
    signal_id: str
    watchlist_id: str
    instrument_symbol: str
    consequence_hint: str
    link_url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
