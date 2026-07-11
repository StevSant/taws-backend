import uuid
from datetime import UTC, datetime

from app.application.quant import UnknownInstrumentError
from app.application.quant.use_cases import ComputeMarketStats
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.notification.entities import ScenarioMatchNotification
from app.domain.notification.ports import NotificationChannel
from app.domain.scenario.entities import ScenarioMagnitude, ScenarioMonitor, ScenarioResult
from app.domain.scenario.ports import ScenarioRepository
from app.domain.signals.entities import ImpactClass
from app.domain.signals.ports import SignalRepository

# Minimum price-history window handed to `ComputeMarketStats` — a shorter window can't
# produce 2 candles to diff, so `price_delta_pct` would always be `None`. See
# `_price_window_days` below for how this combines with "since arming".
_MIN_PRICE_WINDOW_DAYS = 2


class EvaluateScenarioMonitors:
    """Watchdog/Notifier sibling use case (issue #18): evaluates every armed
    `ScenarioMonitor` on Watchdog's scheduled pass, checking whether the originating
    scenario looks like it's actually materializing.

    Shared by the scheduler's periodic job (`infrastructure/scheduling/
    watchdog_scheduler.py`) and the manual "Evaluate now" endpoint
    (`POST /api/v1/watchdog/evaluate-scenarios`) — same use case, same logic, exactly the
    same pattern `RunWatchdogScan` already establishes for signal alerts.

    ## Matching rule (deliberately simple — "did a real signal or big move happen on one
    of this scenario's affected symbols since arming", NOT semantic similarity)

    For each `ARMED` monitor, for each of the scenario's `spec.affected_symbols`, in order,
    the FIRST of these two checks that fires wins (short-circuits — one hit is enough):

    1. **Signal match**: a `Signal` was created for that symbol AFTER the monitor was armed
       (`Signal.created_at >= monitor.armed_at`, via `SignalRepository.list_for_instrument`)
       whose `impact_class` equals the scenario's OWN expected direction for that symbol's
       asset class — i.e. `ScenarioResult.impact_map`'s entry for that `AssetClass` (the
       Synthesis step's own directional call for this scenario, issue #12), not some
       separately-invented "expected direction" field. A `NEUTRAL`/`UNCERTAIN` expected
       direction, or a symbol whose asset class isn't in the scenario's impact map, can't be
       matched this way (there's nothing directional to confirm) — falls through to the
       price check.

    2. **Price-move match**: `ComputeMarketStats.execute(symbol, window_days=...)`'s
       `price_delta_pct` (issue #7 — reused as-is, not reimplemented) has an absolute value
       at or above the threshold mapped from the scenario's OWN `spec.magnitude`:

       | magnitude | threshold |
       |-----------|-----------|
       | low       | 2%        |
       | medium    | 5%        |
       | high      | 10%       |

       (Config-driven via `Settings.scenario_monitor_price_move_threshold_{low,medium,
       high}_pct` — these are the documented defaults, not hardcoded here.) Direction is
       deliberately NOT checked for this branch: a large move either way on an affected
       symbol is itself evidence "something dramatic is happening" there, which is what
       the price-move criterion is for — direction confirmation is the signal check's job.
       The window is "since arming" (`(now - monitor.armed_at).days`, floored at
       `_MIN_PRICE_WINDOW_DAYS` so there's a chance of 2 candles, capped at
       `Settings.scenario_monitor_price_window_max_days` so a monitor armed months ago
       doesn't request an enormous history fetch).

    A symbol not in the curated `InstrumentUniverse` (can't resolve its asset class or
    fetch stats for it) is skipped with a warning — same "unknown instrument" boundary
    `ComputeMarketStats`/`UnknownInstrumentError` already draw elsewhere.

    On the first match, `EvaluateScenarioMonitors`:
    - calls `ScenarioRepository.mark_monitor_matched(...)` (transitions to `MATCHED` —
      see `ScenarioMonitor`'s docstring for why this doesn't delete/disarm), and
    - composes and delivers a `ScenarioMatchNotification` via `NotificationChannel.
      send_scenario_match(...)`.

    A monitor whose `expires_at` has passed is transitioned to `EXPIRED` (via
    `mark_monitor_expired`) and skipped for the rest of this pass — no notification for a
    plain expiry, only for a match.

    Never produces trading/execution instructions — same compliance stance as
    `RunWatchdogScan`/every other agent output in this codebase; a match is an
    informational "this scenario looks like it might be happening — worth reviewing" call.
    """

    def __init__(
        self,
        scenario_repository: ScenarioRepository,
        signal_repository: SignalRepository,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        notification_channel: NotificationChannel,
        frontend_base_url: str,
        price_move_threshold_low_pct: float,
        price_move_threshold_medium_pct: float,
        price_move_threshold_high_pct: float,
        price_window_max_days: int,
    ) -> None:
        self._scenario_repository = scenario_repository
        self._signal_repository = signal_repository
        self._compute_market_stats = ComputeMarketStats(
            market_data_provider=market_data_provider, instrument_universe=instrument_universe
        )
        self._instrument_universe = instrument_universe
        self._notification_channel = notification_channel
        self._frontend_base_url = frontend_base_url
        self._price_move_threshold_pct = {
            ScenarioMagnitude.LOW: price_move_threshold_low_pct,
            ScenarioMagnitude.MEDIUM: price_move_threshold_medium_pct,
            ScenarioMagnitude.HIGH: price_move_threshold_high_pct,
        }
        self._price_window_max_days = price_window_max_days

    async def execute(self) -> list[ScenarioMonitor]:
        """Evaluate every armed monitor and return the ones that matched this pass
        (mirrors `RunWatchdogScan.execute()`'s "return what fired" shape)."""
        matched: list[ScenarioMonitor] = []
        for monitor in await self._scenario_repository.list_armed_monitors():
            result = await self._evaluate_monitor(monitor)
            if result is not None:
                matched.append(result)
        return matched

    async def _evaluate_monitor(self, monitor: ScenarioMonitor) -> ScenarioMonitor | None:
        now = datetime.now(UTC)
        if now >= monitor.expires_at:
            await self._scenario_repository.mark_monitor_expired(monitor.id)
            return None

        scenario = await self._scenario_repository.get(monitor.scenario_id)
        if scenario is None:
            # The scenario was deleted out from under an armed monitor — nothing to
            # evaluate against. Left ARMED rather than force-expired: not this pass's call
            # to make a data-integrity decision, just skip it this tick.
            return None

        match_reason = await self._find_match_reason(monitor, scenario)
        if match_reason is None:
            return None

        matched_monitor = await self._scenario_repository.mark_monitor_matched(
            monitor.id, match_reason
        )
        await self._notification_channel.send_scenario_match(
            _compose_notification(matched_monitor, scenario, match_reason, self._frontend_base_url)
        )
        return matched_monitor

    async def _find_match_reason(
        self, monitor: ScenarioMonitor, scenario: ScenarioResult
    ) -> str | None:
        for symbol in scenario.spec.affected_symbols:
            instrument = self._instrument_universe.by_symbol(symbol)
            if instrument is None:
                continue

            signal_reason = await self._check_signal_match(monitor, scenario, instrument)
            if signal_reason is not None:
                return signal_reason

            price_reason = await self._check_price_match(monitor, scenario, instrument)
            if price_reason is not None:
                return price_reason
        return None

    async def _check_signal_match(
        self, monitor: ScenarioMonitor, scenario: ScenarioResult, instrument: Instrument
    ) -> str | None:
        expected_direction = _expected_direction_for_asset_class(scenario, instrument.asset_class)
        if expected_direction is None:
            return None

        new_signals = [
            signal
            for signal in await self._signal_repository.list_for_instrument(instrument.symbol)
            if signal.created_at >= monitor.armed_at
        ]
        matching_signal = next(
            (s for s in new_signals if s.impact_class == expected_direction), None
        )
        if matching_signal is None:
            return None
        return (
            f"{instrument.symbol} produced a new {matching_signal.impact_class.value} signal "
            f"(confidence {matching_signal.confidence:.0%}) since the monitor was armed — "
            f"matches the scenario's expected {expected_direction.value} impact on "
            f"{instrument.asset_class.value}."
        )

    async def _check_price_match(
        self, monitor: ScenarioMonitor, scenario: ScenarioResult, instrument: Instrument
    ) -> str | None:
        threshold_pct = self._price_move_threshold_pct[scenario.spec.magnitude]
        window_days = _price_window_days(monitor.armed_at, self._price_window_max_days)
        try:
            stats = await self._compute_market_stats.execute(
                instrument.symbol, window_days=window_days
            )
        except UnknownInstrumentError:
            return None
        if stats.price_delta_pct is None or abs(stats.price_delta_pct) < threshold_pct:
            return None
        return (
            f"{instrument.symbol} moved {stats.price_delta_pct:+.2f}% over the last "
            f"{window_days} day(s) since the monitor was armed — crosses the "
            f"{scenario.spec.magnitude.value}-magnitude threshold of {threshold_pct:.0f}%."
        )


def _expected_direction_for_asset_class(
    scenario: ScenarioResult, asset_class: AssetClass
) -> ImpactClass | None:
    """The scenario's OWN directional call for this asset class (from its `impact_map`,
    the Synthesis step's output — issue #12), or `None` if the scenario didn't call one out
    for this asset class, or called out `NEUTRAL`/`UNCERTAIN` (nothing directional to
    confirm against a new `Signal`)."""
    for impact in scenario.impact_map:
        if impact.asset_class != asset_class:
            continue
        if impact.direction in (ImpactClass.NEUTRAL, ImpactClass.UNCERTAIN):
            return None
        return impact.direction
    return None


def _price_window_days(armed_at: datetime, max_days: int) -> int:
    """ "Since arming" window, floored so there's a chance of 2 candles to diff and capped
    so a long-armed monitor doesn't request an unbounded price history."""
    days_since_armed = (datetime.now(UTC) - armed_at).days
    return max(_MIN_PRICE_WINDOW_DAYS, min(days_since_armed, max_days))


def _compose_notification(
    monitor: ScenarioMonitor, scenario: ScenarioResult, match_reason: str, frontend_base_url: str
) -> ScenarioMatchNotification:
    return ScenarioMatchNotification(
        id=str(uuid.uuid4()),
        monitor_id=monitor.id,
        scenario_id=scenario.id,
        user_id=monitor.user_id,
        scenario_title=scenario.title,
        match_reason=match_reason,
        # No scenario-detail route exists in the frontend yet (see issue #18's follow-up
        # frontend issue) — links back to the Scenario Lab list page with an `id` query
        # param a future detail view can read, same "config-driven base, never hardcoded"
        # rule `Alert.link_url`/`BriefingReadyNotification.link_url` follow.
        link_url=f"{frontend_base_url.rstrip('/')}/scenarios?id={scenario.id}",
    )
