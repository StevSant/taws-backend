class AlertedSignalTracker:
    """Tracks which signal ids have already produced a Watchdog alert, in-process.

    This is the "novelty" half of notification-worthiness (see
    `RunWatchdogScan._is_notification_worthy`): a signal that already triggered an alert
    shouldn't trigger a second one on the next scan. Backed by a plain in-memory set —
    deliberately NOT a persisted table: this is a T1-scope, demo-safe dedup guard, not a
    durable audit trail. It resets on every process restart, so a fresh deploy may re-alert
    on signals seen before the restart; a persisted `alerted_signals` table would be the
    natural upgrade if this needs to survive restarts, but that's over-engineering for this
    issue's scope.

    One instance is shared (via `Container.get_alerted_signal_tracker()`) between the
    scheduler's periodic scan job and the manual "Scan now" endpoint, so both draw from the
    same dedup state.
    """

    def __init__(self) -> None:
        self._alerted_signal_ids: set[str] = set()

    def is_new(self, signal_id: str) -> bool:
        """Return `True` if this signal id hasn't already produced an alert."""
        return signal_id not in self._alerted_signal_ids

    def mark_alerted(self, signal_id: str) -> None:
        """Record that this signal id has now produced an alert."""
        self._alerted_signal_ids.add(signal_id)
