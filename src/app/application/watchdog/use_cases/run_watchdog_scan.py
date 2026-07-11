import uuid

from app.application.watchdog.alerted_signal_tracker import AlertedSignalTracker
from app.domain.notification.entities import Alert
from app.domain.notification.ports import NotificationChannel
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist
from app.domain.watchlist.ports import WatchlistRepository


class RunWatchdogScan:
    """Watchdog/Notifier pipeline (issue #10): scans every watchlist for notification-worthy
    signals and hands composed `Alert`s to the `NotificationChannel` port.

    Shared by both the scheduler's periodic job (`infrastructure/scheduling`) and the manual
    "Scan now" endpoint (`POST /api/v1/watchdog/scan`) — same use case, same logic, so a
    demo-triggered scan behaves identically to a scheduled one. Global (not user-scoped):
    reads every watchlist via `WatchlistRepository.list_all()`, since a scheduled scan has no
    single request-bound user to scope to — same "not user-scoped" shape as `GenerateSignal`.

    Never produces trading/execution instructions — an alert is an informational surfacing of
    an already-persisted `Signal`, same compliance stance as `Signal`/`Briefing` themselves.
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        signal_repository: SignalRepository,
        notification_channel: NotificationChannel,
        alerted_signal_tracker: AlertedSignalTracker,
        frontend_base_url: str,
        min_confidence: float,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._signal_repository = signal_repository
        self._notification_channel = notification_channel
        self._alerted_signal_tracker = alerted_signal_tracker
        self._frontend_base_url = frontend_base_url
        self._min_confidence = min_confidence

    async def execute(self) -> list[Alert]:
        watchlists = await self._watchlist_repository.list_all()
        alerts: list[Alert] = []
        for watchlist in watchlists:
            alerts.extend(await self._scan_watchlist(watchlist))
        return alerts

    async def _scan_watchlist(self, watchlist: Watchlist) -> list[Alert]:
        items = await self._watchlist_repository.list_items(watchlist.id)
        alerts: list[Alert] = []
        for item in items:
            signals = await self._signal_repository.list_for_instrument(item.symbol)
            for signal in signals:
                if not self._is_notification_worthy(signal):
                    continue
                alert = _compose_alert(signal, watchlist, self._frontend_base_url)
                await self._notification_channel.send(alert)
                self._alerted_signal_tracker.mark_alerted(signal.id)
                alerts.append(alert)
        return alerts

    def _is_notification_worthy(self, signal: Signal) -> bool:
        """T1 notification-worthiness rule — deliberately simple, not a scoring model:

        1. severity: `impact_class` is not "neutral" (a directional call, not a no-op read).
        2. confidence: at least `_min_confidence` (config-driven,
           `Settings.watchdog_min_confidence`).
        3. novelty: this signal id hasn't already produced an alert this process's lifetime
           (`AlertedSignalTracker.is_new`).

        All three must hold. See `AlertedSignalTracker`'s docstring for why novelty is tracked
        in-process rather than via a persisted dedup table.
        """
        if signal.impact_class == ImpactClass.NEUTRAL:
            return False
        if signal.confidence < self._min_confidence:
            return False
        return self._alerted_signal_tracker.is_new(signal.id)


def _compose_alert(signal: Signal, watchlist: Watchlist, frontend_base_url: str) -> Alert:
    return Alert(
        id=str(uuid.uuid4()),
        signal_id=signal.id,
        watchlist_id=watchlist.id,
        instrument_symbol=signal.instrument_symbol,
        consequence_hint=_derive_consequence_hint(signal),
        link_url=f"{frontend_base_url.rstrip('/')}/watchlists/{watchlist.id}?signal={signal.id}",
    )


_IMPACT_DIRECTION_PHRASES = {
    ImpactClass.POSITIVE: "a positive",
    ImpactClass.NEGATIVE: "a negative",
    ImpactClass.UNCERTAIN: "an uncertain",
}


def _derive_consequence_hint(signal: Signal) -> str:
    """Short, non-committal hint derived strictly from the signal's own evidence.

    NOT a call to the Consequence Chain agent (issue #8) — that agent is optional/nice-to-have
    and not hard-depended on here since it may not be merged yet. Never invents facts and never
    phrases anything as a trade instruction.
    """
    direction = _IMPACT_DIRECTION_PHRASES.get(signal.impact_class, "a")
    lead_source = signal.evidence[0].source if signal.evidence else "recent market activity"
    return (
        f"{signal.instrument_symbol} shows {direction} impact signal "
        f"(confidence {signal.confidence:.0%}), based on {lead_source}. Worth reviewing — "
        "not a trade instruction."
    )
