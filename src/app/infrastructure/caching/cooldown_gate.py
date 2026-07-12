import logging
import time

logger = logging.getLogger(__name__)


class CooldownGate:
    """Simple circuit breaker: once tripped, blocks callers until a cool-down expires.

    Used to stop hammering a third-party API after a clearly non-transient failure
    (e.g. Marketaux returning 402/401/429, issue #9) instead of retrying on every poll.
    `trip()` only logs a warning the first time it's called while the gate is closed —
    callers are expected to check `is_open()` before making the call in the first place
    (see `MarketauxNewsProvider.fetch_news`), so once tripped, subsequent poll cycles
    skip the call (and this class) entirely and never log anything — exactly one
    warning per cool-down period, not one per skipped attempt.
    """

    def __init__(self) -> None:
        self._blocked_until: float | None = None

    def is_open(self) -> bool:
        """True while a previously tripped cool-down is still in effect."""
        return self._blocked_until is not None and time.monotonic() < self._blocked_until

    def trip(self, cooldown_seconds: float, reason: str) -> None:
        """Enter cool-down for `cooldown_seconds` from now, logging one warning.

        Safe to call repeatedly (e.g. once per failed request) — only the call that
        actually transitions the gate from closed to open logs anything, so callers
        don't need to guard this with their own `is_open()` check first.
        """
        was_open = self.is_open()
        self._blocked_until = time.monotonic() + cooldown_seconds
        if not was_open:
            logger.warning("Entering %.0fs cool-down: %s", cooldown_seconds, reason)
