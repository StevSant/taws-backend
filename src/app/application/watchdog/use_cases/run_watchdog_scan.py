import uuid

from app.application.profile.use_cases import ResolveLocale
from app.application.watchdog.alerted_signal_tracker import AlertedSignalTracker
from app.application.watchdog.derive_consequence_hint import derive_consequence_hint
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

    **Only the newest signal per instrument is considered.** This used to call
    `SignalRepository.list_for_instrument`, which returns EVERY historical row for a symbol —
    and since the shared-analysis refresh job regenerates signals on a timer while
    `ANALYSIS_RETENTION_KEEP` retains several rows per `(symbol, locale)`, one scan walked a
    pile of stale, superseded calls and alerted on each it hadn't seen before. Together with
    the old id-keyed dedup guard (see `AlertedSignalTracker`) that made the same ticker alert
    over and over at drifting confidences, burying the user's own chat with the bot. A
    watchlist item has exactly one current call; `get_latest_for_instrument` is that call, and
    it is the only one worth notifying anyone about.

    Signals are persisted per locale, so reading "the latest signal" means knowing WHICH
    locale to read — the watchlist owner's, resolved once per watchlist. That same locale is
    stamped onto the `Alert`, so the delivery adapter can write the whole message in the
    recipient's language instead of the English-only text every user used to receive.
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        signal_repository: SignalRepository,
        notification_channel: NotificationChannel,
        alerted_signal_tracker: AlertedSignalTracker,
        resolve_locale: ResolveLocale,
        frontend_base_url: str,
        min_confidence: float,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._signal_repository = signal_repository
        self._notification_channel = notification_channel
        self._alerted_signal_tracker = alerted_signal_tracker
        self._resolve_locale = resolve_locale
        self._frontend_base_url = frontend_base_url
        self._min_confidence = min_confidence

    async def execute(self) -> list[Alert]:
        watchlists = await self._watchlist_repository.list_all()
        alerts: list[Alert] = []
        for watchlist in watchlists:
            alerts.extend(await self._scan_watchlist(watchlist))
        return alerts

    async def _scan_watchlist(self, watchlist: Watchlist) -> list[Alert]:
        locale = await self._resolve_locale.execute(user_id=watchlist.user_id)
        items = await self._watchlist_repository.list_items(watchlist.id)
        alerts: list[Alert] = []
        for item in items:
            signal = await self._signal_repository.get_latest_for_instrument(item.symbol, locale)
            if signal is None or not self._is_notification_worthy(signal, watchlist.id):
                continue

            alert = _compose_alert(signal, watchlist, locale, self._frontend_base_url)
            await self._notification_channel.send(alert)
            self._alerted_signal_tracker.mark_alerted(
                watchlist.id, signal.instrument_symbol, signal.impact_class
            )
            alerts.append(alert)
        return alerts

    def _is_notification_worthy(self, signal: Signal, watchlist_id: str) -> bool:
        """T1 notification-worthiness rule — deliberately simple, not a scoring model:

        1. severity: `impact_class` is not "neutral" (a directional call, not a no-op read).
        2. confidence: at least `_min_confidence` (config-driven,
           `Settings.watchdog_min_confidence`).
        3. novelty: this instrument's call is new, has flipped direction, or has gone stale
           enough to resurface (`AlertedSignalTracker.should_alert`).

        All three must hold. See `AlertedSignalTracker`'s docstring for why novelty is keyed on
        `(watchlist, symbol)` rather than on the signal id, and why it's tracked in-process
        rather than in a persisted dedup table.
        """
        if signal.impact_class == ImpactClass.NEUTRAL:
            return False
        if signal.confidence < self._min_confidence:
            return False
        return self._alerted_signal_tracker.should_alert(
            watchlist_id, signal.instrument_symbol, signal.impact_class
        )


def _compose_alert(
    signal: Signal, watchlist: Watchlist, locale: str, frontend_base_url: str
) -> Alert:
    return Alert(
        id=str(uuid.uuid4()),
        signal_id=signal.id,
        watchlist_id=watchlist.id,
        instrument_symbol=signal.instrument_symbol,
        consequence_hint=derive_consequence_hint(signal, locale),
        # Points at the asset detail page (`radar/:symbol`, see the frontend's
        # `radar.routes.ts`). It used to point at `/watchlists/{id}?signal={id}` — a route that
        # has never existed in the Angular router, whose `WATCHLISTS_ROUTES` only ever declared
        # `path: ''`. With nothing to match and no wildcard route, every alert link a user
        # tapped rendered a blank white page. The asset page is the more useful destination
        # anyway: it shows the instrument the alert is actually about.
        link_url=f"{frontend_base_url.rstrip('/')}/radar/{signal.instrument_symbol}",
        locale=locale,
    )
