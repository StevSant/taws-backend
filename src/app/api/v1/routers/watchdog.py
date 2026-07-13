from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    get_alerted_signal_tracker,
    get_instrument_universe,
    get_market_data_provider,
    get_notification_channel,
    get_resolve_locale_use_case,
    get_scenario_repository,
    get_signal_repository,
    get_watchlist_repository,
)
from app.api.v1.schemas import AlertResponse, ScenarioMonitorResponse
from app.application.profile.use_cases import ResolveLocale
from app.application.watchdog import AlertedSignalTracker
from app.application.watchdog.use_cases import EvaluateScenarioMonitors, RunWatchdogScan
from app.core.config import Settings, get_settings
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.domain.notification.ports import NotificationChannel
from app.domain.scenario.ports import ScenarioRepository
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(prefix="/watchdog", tags=["watchdog"])


@router.post("/scan", status_code=status.HTTP_200_OK)
async def scan_now(
    settings: Annotated[Settings, Depends(get_settings)],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    notification_channel: Annotated[NotificationChannel, Depends(get_notification_channel)],
    alerted_signal_tracker: Annotated[AlertedSignalTracker, Depends(get_alerted_signal_tracker)],
    resolve_locale: Annotated[ResolveLocale, Depends(get_resolve_locale_use_case)],
) -> list[AlertResponse]:
    """Trigger one Watchdog scan pass immediately (demo-safe manual "Scan now" trigger).

    Runs the SAME `RunWatchdogScan` use case the scheduler's periodic job calls (see
    `infrastructure/scheduling`), so a manual scan behaves identically to a scheduled one —
    no duplicated scan logic. Not user-scoped (a global scan across every watchlist), same
    visibility model as `POST /api/v1/signals/generate`.
    """
    use_case = RunWatchdogScan(
        watchlist_repository=watchlist_repository,
        signal_repository=signal_repository,
        notification_channel=notification_channel,
        alerted_signal_tracker=alerted_signal_tracker,
        resolve_locale=resolve_locale,
        frontend_base_url=settings.frontend_base_url,
        min_confidence=settings.watchdog_min_confidence,
    )
    alerts = await use_case.execute()
    return [AlertResponse.model_validate(alert) for alert in alerts]


@router.post("/evaluate-scenarios", status_code=status.HTTP_200_OK)
async def evaluate_scenario_monitors_now(
    settings: Annotated[Settings, Depends(get_settings)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    notification_channel: Annotated[NotificationChannel, Depends(get_notification_channel)],
) -> list[ScenarioMonitorResponse]:
    """Trigger one Scenario Monitor evaluation pass immediately (issue #18) — demo-safe
    manual trigger, same "on-demand endpoint runs the exact scheduled-job use case" pattern
    `POST /api/v1/watchdog/scan` establishes for `RunWatchdogScan`.
    """
    use_case = EvaluateScenarioMonitors(
        scenario_repository=scenario_repository,
        signal_repository=signal_repository,
        market_data_provider=market_data_provider,
        instrument_universe=instrument_universe,
        notification_channel=notification_channel,
        frontend_base_url=settings.frontend_base_url,
        price_move_threshold_low_pct=settings.scenario_monitor_price_move_threshold_low_pct,
        price_move_threshold_medium_pct=settings.scenario_monitor_price_move_threshold_medium_pct,
        price_move_threshold_high_pct=settings.scenario_monitor_price_move_threshold_high_pct,
        price_window_max_days=settings.scenario_monitor_price_window_max_days,
    )
    matched_monitors = await use_case.execute()
    return [ScenarioMonitorResponse.model_validate(monitor) for monitor in matched_monitors]
