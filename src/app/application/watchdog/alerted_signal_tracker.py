from datetime import UTC, datetime, timedelta

from app.domain.signals.entities import ImpactClass


class AlertedSignalTracker:
    """Tracks what the Watchdog has already alerted on, so a scan never re-notifies noise.

    Keyed by `(watchlist_id, instrument_symbol)` — deliberately NOT by `signal.id`.

    **Why the key is not the signal id.** It used to be, and that only looked like a novelty
    guard. The shared-analysis refresh job (issue #29) regenerates a signal for every
    watchlisted instrument on its own cadence, and `ANALYSIS_RETENTION_KEEP` keeps several
    historical rows per `(symbol, locale)`. Every regenerated row carries a fresh uuid, so an
    id-keyed guard judged each one "new" and fired another Telegram alert for the *same
    instrument* minutes later at a slightly different confidence — the observed failure was
    one ticker alerting twice inside a single conversation (75%, then 80%), burying the
    user's own chat with the bot. The unit a human cares about is "this instrument, this
    direction", not "this database row".

    Re-alerting a key is allowed only when the call has actually **changed** (a different
    `ImpactClass` — a flip from positive to negative genuinely is worth interrupting someone
    for) or when `cooldown` has elapsed (so a still-true call can resurface once it is stale
    news, rather than on every scan tick).

    Backed by a plain in-process dict — the same T1-scope tradeoff as before: it resets on
    restart, so a fresh deploy may re-alert once on calls seen before it. A persisted
    `alerted_signals` table is the natural upgrade; until then the cooldown bounds a restart's
    blast radius to one message per instrument instead of one per retained signal row.

    One instance is shared (via `Container.get_alerted_signal_tracker()`) between the
    scheduler's periodic scan job and the manual "Scan now" endpoint, so both draw from the
    same dedup state.
    """

    def __init__(self, cooldown: timedelta) -> None:
        self._cooldown = cooldown
        # (watchlist_id, symbol) -> (the impact class alerted, when it was alerted)
        self._last_alerted: dict[tuple[str, str], tuple[ImpactClass, datetime]] = {}

    def should_alert(
        self, watchlist_id: str, instrument_symbol: str, impact_class: ImpactClass
    ) -> bool:
        """Return `True` if this instrument's current call is worth interrupting the user for.

        True when nothing has been alerted for this `(watchlist, symbol)` yet, when the
        direction differs from the one last alerted, or when the cooldown has expired.
        """
        previous = self._last_alerted.get((watchlist_id, instrument_symbol))
        if previous is None:
            return True

        previous_impact, alerted_at = previous
        if previous_impact != impact_class:
            return True
        return datetime.now(UTC) - alerted_at >= self._cooldown

    def mark_alerted(
        self, watchlist_id: str, instrument_symbol: str, impact_class: ImpactClass
    ) -> None:
        """Record that this instrument's current call has now produced an alert."""
        self._last_alerted[(watchlist_id, instrument_symbol)] = (impact_class, datetime.now(UTC))
