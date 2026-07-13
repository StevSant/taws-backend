from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class Alert:
    """A Watchdog/Notifier-agent-composed notification for one notification-worthy `Signal`.

    Produced by `RunWatchdogScan` (`application/watchdog/use_cases/run_watchdog_scan.py`) and
    handed to a `NotificationChannel` port adapter for delivery. Informational only — an alert
    surfaces an already-persisted `Signal`, it is never a trading/execution instruction.

    `consequence_hint` is a short, plain-language string derived from the signal's own
    evidence (see `derive_consequence_hint` in `application/watchdog/`) — NOT a call to the
    Consequence Chain agent (issue #8, optional/nice-to-have, not hard-depended on here).
    `link_url` points back to the app (config-driven base URL, `Settings.frontend_base_url`),
    never a hardcoded frontend URL.

    `locale` is the language `consequence_hint` is already written in, and the language the
    delivery adapter must render the rest of the message in (header, link label, disclaimer) so
    a single alert is never half Spanish and half English. It is the watchlist OWNER's locale,
    resolved when the alert is composed: a scheduled scan has no request to read a locale from,
    and the owner is the only person who will ever see this text.
    """

    id: str
    signal_id: str
    watchlist_id: str
    instrument_symbol: str
    consequence_hint: str
    link_url: str
    locale: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
