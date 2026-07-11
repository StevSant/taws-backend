import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.application.briefing.use_cases import GenerateBriefing
from app.application.watchdog.use_cases import RunDailyBriefings, RunWatchdogScan
from app.core.config import Settings
from app.core.di import Container

logger = logging.getLogger(__name__)

_SCAN_JOB_ID = "watchdog-scan"
_DAILY_BRIEFINGS_JOB_ID = "watchdog-daily-briefings"


async def _run_scan_job(container: Container, settings: Settings) -> None:
    """Periodic Watchdog scan job — the SAME `RunWatchdogScan` use case that
    `POST /api/v1/watchdog/scan` triggers on demand (see `api/v1/routers/watchdog.py`)."""
    use_case = RunWatchdogScan(
        watchlist_repository=container.get_watchlist_repository(),
        signal_repository=container.get_signal_repository(),
        notification_channel=container.get_notification_channel(),
        alerted_signal_tracker=container.get_alerted_signal_tracker(),
        frontend_base_url=settings.frontend_base_url,
        min_confidence=settings.watchdog_min_confidence,
    )
    try:
        alerts = await use_case.execute()
        logger.info("watchdog scan complete: %d alert(s) composed", len(alerts))
    except Exception:  # noqa: BLE001 — a bad scan must never crash the scheduler thread
        logger.exception("watchdog scan job failed")


async def _run_daily_briefings_job(container: Container, settings: Settings) -> None:
    """Daily briefing job — reuses the existing `GenerateBriefing` use case (issue #3) via
    `RunDailyBriefings`, one active watchlist at a time."""
    generate_briefing = GenerateBriefing(
        watchlist_repository=container.get_watchlist_repository(),
        signal_repository=container.get_signal_repository(),
        briefing_repository=container.get_briefing_repository(),
        llm_provider=container.get_llm_provider(),
    )
    use_case = RunDailyBriefings(
        watchlist_repository=container.get_watchlist_repository(),
        generate_briefing=generate_briefing,
    )
    try:
        briefings = await use_case.execute()
        logger.info("daily briefing run complete: %d briefing(s) generated", len(briefings))
    except Exception:  # noqa: BLE001 — same resilience guarantee as the scan job
        logger.exception("daily briefing job failed")


def build_watchdog_scheduler(container: Container, settings: Settings) -> AsyncIOScheduler:
    """Build (but don't start) the process-wide APScheduler for the Watchdog/Notifier agent.

    Two config-driven jobs, both reusing the SAME application use cases as their on-demand
    HTTP counterparts — no duplicated scan/briefing logic:

    - `watchdog-scan` (`RunWatchdogScan`, every `settings.watchdog_poll_interval_minutes`
      minutes): the same pass `POST /api/v1/watchdog/scan` triggers manually.
    - `watchdog-daily-briefings` (`RunDailyBriefings`, once a day at
      `settings.watchdog_daily_briefing_hour_utc`:`watchdog_daily_briefing_minute_utc` UTC):
      regenerates an Advisor briefing for every active watchlist.

    `AsyncIOScheduler` (not a background thread pool) integrates directly with FastAPI's
    asyncio event loop; `max_instances=1` on each job prevents a slow run from overlapping
    with the next tick. APScheduler is a vendor concern, deliberately kept out of
    `domain/`/`application/` — this is the wiring/adapter layer. The caller (`main.py`'s
    `_lifespan`) only ever calls `.start()`/`.shutdown()`.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_scan_job,
        trigger=IntervalTrigger(minutes=settings.watchdog_poll_interval_minutes),
        args=(container, settings),
        id=_SCAN_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_daily_briefings_job,
        trigger=CronTrigger(
            hour=settings.watchdog_daily_briefing_hour_utc,
            minute=settings.watchdog_daily_briefing_minute_utc,
        ),
        args=(container, settings),
        id=_DAILY_BRIEFINGS_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    return scheduler
