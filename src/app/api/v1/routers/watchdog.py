from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    get_alerted_signal_tracker,
    get_notification_channel,
    get_signal_repository,
    get_watchlist_repository,
)
from app.api.v1.schemas import AlertResponse
from app.application.watchdog import AlertedSignalTracker
from app.application.watchdog.use_cases import RunWatchdogScan
from app.core.config import Settings, get_settings
from app.domain.notification.ports import NotificationChannel
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
        frontend_base_url=settings.frontend_base_url,
        min_confidence=settings.watchdog_min_confidence,
    )
    alerts = await use_case.execute()
    return [AlertResponse.model_validate(alert) for alert in alerts]
