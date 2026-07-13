import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.application.briefing.use_cases import GenerateBriefing
from app.application.watchdog.use_cases import (
    EvaluateScenarioMonitors,
    RunDailyBriefings,
    RunWatchdogScan,
)
from app.core.config import Settings
from app.core.di import Container

logger = logging.getLogger(__name__)

_SCAN_JOB_ID = "watchdog-scan"
_DAILY_BRIEFINGS_JOB_ID = "watchdog-daily-briefings"
_EVALUATE_SCENARIO_MONITORS_JOB_ID = "watchdog-evaluate-scenario-monitors"
_ANALYZE_PENDING_NEWS_JOB_ID = "analyze-pending-news"
_REFRESH_ANALYSIS_JOB_ID = "refresh-tracked-analysis"
_SENTINEL_SCAN_JOB_ID = "sentinel-news-scan"
_SCORE_NEWS_SENTIMENT_JOB_ID = "score-news-sentiment"


async def _run_scan_job(container: Container, settings: Settings) -> None:
    """Periodic Watchdog scan job — the SAME `RunWatchdogScan` use case that
    `POST /api/v1/watchdog/scan` triggers on demand (see `api/v1/routers/watchdog.py`)."""
    use_case = RunWatchdogScan(
        watchlist_repository=container.get_watchlist_repository(),
        signal_repository=container.get_signal_repository(),
        notification_channel=container.get_notification_channel(),
        alerted_signal_tracker=container.get_alerted_signal_tracker(),
        resolve_locale=container.get_resolve_locale_use_case(),
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
    `RunDailyBriefings`, one active watchlist at a time, then notifies each watchlist's
    owner over Telegram (issue #16) via the same `NotificationChannel` port the scan job
    uses."""
    generate_briefing = GenerateBriefing(
        watchlist_repository=container.get_watchlist_repository(),
        signal_repository=container.get_signal_repository(),
        briefing_repository=container.get_briefing_repository(),
        # Reasoning tier (#28) — matches what `POST /api/v1/briefings` uses, so a scheduled
        # briefing and a manually-triggered one are composed by the same model.
        llm_provider=container.get_reasoning_llm_provider(),
    )
    use_case = RunDailyBriefings(
        watchlist_repository=container.get_watchlist_repository(),
        generate_briefing=generate_briefing,
        notification_channel=container.get_notification_channel(),
        frontend_base_url=settings.frontend_base_url,
    )
    try:
        briefings = await use_case.execute(locale=settings.default_locale)
        logger.info("daily briefing run complete: %d briefing(s) generated", len(briefings))
    except Exception:  # noqa: BLE001 — same resilience guarantee as the scan job
        logger.exception("daily briefing job failed")


async def _run_evaluate_scenario_monitors_job(container: Container, settings: Settings) -> None:
    """Periodic Scenario Monitor evaluation job (issue #18) — the SAME
    `EvaluateScenarioMonitors` use case `POST /api/v1/watchdog/evaluate-scenarios` triggers
    on demand (see `api/v1/routers/watchdog.py`). Reuses `settings.
    watchdog_poll_interval_minutes` as its cadence too, rather than adding a second interval
    setting — a scenario materializing is exactly as time-sensitive as a signal alert, so
    there's no product reason for these two passes to run on different schedules."""
    use_case = EvaluateScenarioMonitors(
        scenario_repository=container.get_scenario_repository(),
        signal_repository=container.get_signal_repository(),
        market_data_provider=container.get_market_data_provider(),
        instrument_universe=container.get_instrument_universe(),
        notification_channel=container.get_notification_channel(),
        frontend_base_url=settings.frontend_base_url,
        price_move_threshold_low_pct=settings.scenario_monitor_price_move_threshold_low_pct,
        price_move_threshold_medium_pct=settings.scenario_monitor_price_move_threshold_medium_pct,
        price_move_threshold_high_pct=settings.scenario_monitor_price_move_threshold_high_pct,
        price_window_max_days=settings.scenario_monitor_price_window_max_days,
    )
    try:
        matched = await use_case.execute()
        logger.info("scenario monitor evaluation complete: %d monitor(s) matched", len(matched))
    except Exception:  # noqa: BLE001 — a bad evaluation pass must never crash the scheduler
        logger.exception("scenario monitor evaluation job failed")


async def _run_analyze_pending_news_job(container: Container, settings: Settings) -> None:
    """Periodic pending-news analysis tick (issue #2) — the SAME `AnalyzePendingNews` use
    case `POST /api/v1/news/analyze-pending` triggers on demand (see
    `api/v1/routers/news.py`), so news ingested while nobody is on the page still gets
    classified instead of sitting `pending` until a user happens to click "analyze"."""
    use_case = container.get_analyze_pending_news_use_case()
    try:
        result = await use_case.execute(locale=settings.default_locale)
        logger.info(
            "analyze-pending-news tick complete: %d analyzed, %d skipped, %d failed. "
            "Skipped by reason: %s. Failed by reason: %s.",
            result.analyzed_count,
            result.skipped_count,
            result.failed_count,
            result.skipped_by_reason or "none",
            result.failed_by_reason or "none",
        )
    except Exception:  # noqa: BLE001 — same resilience guarantee as the other scheduled jobs
        logger.exception("analyze-pending-news job failed")


async def _run_score_news_sentiment_job(container: Container, settings: Settings) -> None:
    """Periodic per-article sentiment tick — fills `news_items.sentiment_score`.

    Doubles as the backfill for the rows that predate this job: the pass selects on
    `sentiment_score IS NULL`, so historical articles and freshly-ingested ones drain through
    the exact same code path. `considered == news_sentiment_batch_limit` in the log below means
    a backlog remains and the next tick has more to do.
    """
    use_case = container.get_score_news_sentiment_use_case()
    try:
        result = await use_case.execute()
        logger.info(
            "score-news-sentiment tick complete: %d considered, %d scored, %d failed.",
            result.considered,
            result.scored,
            result.failed,
        )
    except Exception:  # noqa: BLE001 — same resilience guarantee as the other scheduled jobs
        logger.exception("score-news-sentiment job failed")


async def _run_refresh_tracked_analysis_job(container: Container, settings: Settings) -> None:
    """Periodic shared-analysis refresh tick (issue #29) — the SAME `RefreshTrackedAnalysis`
    use case `POST /api/v1/analysis/refresh` triggers on demand.

    This is what makes the freshness cache a *cache* rather than a lottery: without it, the
    unlucky user who happens to make the first request after a TTL expires pays the full
    pipeline latency inline. With it, analysis is refreshed before anyone asks, and user reads
    only ever serve cached rows.

    Calls the generate use cases with `force=False`, so a tick over still-fresh instruments
    costs a handful of indexed SELECTs and zero LLM calls — which is why the cadence and the
    TTLs don't have to be kept in sync. One tick; the TTL decides staleness.
    """
    use_case = container.get_refresh_tracked_analysis_use_case()
    try:
        result = await use_case.execute()
        logger.info(
            "analysis refresh tick complete: %d symbol(s) x %d locale(s) -> %d refreshed, "
            "%d failed",
            result.symbols,
            result.locales,
            result.refreshed,
            result.failed,
        )
    except Exception:  # noqa: BLE001 — same resilience guarantee as the other scheduled jobs
        logger.exception("analysis refresh job failed")


async def _run_sentinel_scan_job(container: Container, settings: Settings) -> None:
    """Periodic Sentinel scan: poll real news -> Gemini judges importance -> broadcast to
    Telegram.

    This is the automatic path the product wanted and never had. Every piece existed already —
    the Gemini analyzer returns `importance`/`should_notify`, the Telegram links resolve to chat
    ids, this scheduler runs five other jobs — but nothing connected "an important article
    arrived" to "tell the users". The only manual trigger, `POST /telegram/send-test-news`,
    picks a RANDOM article and deliberately ignores importance, because its job is proving the
    wiring works, not judging the news.

    Gated by `settings.sentinel_alerts_enabled` for the same reason as the two jobs below it: it
    spends Gemini tokens unattended AND pushes notifications to every linked user without anyone
    asking, so an operator needs to be able to stop it without losing the Watchdog's alerting.
    """
    use_case = container.get_broadcast_important_events_use_case()
    try:
        broadcast = await use_case.execute()
        logger.info("sentinel scan complete: %d important event(s) broadcast", len(broadcast))
    except Exception:  # noqa: BLE001 — same resilience guarantee as the other scheduled jobs
        logger.exception("sentinel scan job failed")


def build_watchdog_scheduler(container: Container, settings: Settings) -> AsyncIOScheduler:
    """Build (but don't start) the process-wide APScheduler for the Watchdog/Notifier agent
    (and the pending-news analysis tick, which piggybacks on this same scheduler rather
    than standing up a second one — see the module docstring-equivalent note on
    `_run_analyze_pending_news_job`).

    Five config-driven jobs, all reusing the SAME application use cases as their
    on-demand HTTP counterparts — no duplicated scan/briefing/evaluation/analysis logic:

    - `watchdog-scan` (`RunWatchdogScan`, every `settings.watchdog_poll_interval_minutes`
      minutes): the same pass `POST /api/v1/watchdog/scan` triggers manually.
    - `watchdog-daily-briefings` (`RunDailyBriefings`, once a day at
      `settings.watchdog_daily_briefing_hour_utc`:`watchdog_daily_briefing_minute_utc` UTC):
      regenerates an Advisor briefing for every active watchlist.
    - `watchdog-evaluate-scenario-monitors` (`EvaluateScenarioMonitors`, issue #18, same
      `watchdog_poll_interval_minutes` cadence as the scan job): checks every armed
      `ScenarioMonitor` for a materializing signal/price-move match.
    - `analyze-pending-news` (`AnalyzePendingNews`, issue #2, every
      `settings.news_analysis_poll_interval_minutes` minutes): the same batch pass
      `POST /api/v1/news/analyze-pending` triggers manually. This is the ONLY job behind an
      enable/disable switch (`settings.news_analysis_enabled`, issue #68): it's the one that
      spends money unattended — each tick can fan out up to `news_analysis_max_concurrency`
      LLM classification calls — so an operator needs to be able to stop the background spend
      without also losing the Watchdog's alerting. Disabling it doesn't disable analysis
      itself: `POST /api/v1/news/analyze-pending` and the per-item `POST /news/{id}/analyze`
      ("Analizar ahora", issue #27) both keep working on demand.
    - `refresh-tracked-analysis` (`RefreshTrackedAnalysis`, issue #29, every
      `settings.analysis_refresh_poll_interval_minutes` minutes): keeps every watchlisted
      instrument's signal + sentiment warm per configured locale, so user reads never trigger
      an inline LLM run. Gated by `settings.analysis_refresh_enabled` for the same reason as
      the job above — it spends tokens unattended. Note the freshness gate lives inside the
      generate use cases, so a tick over already-fresh instruments costs zero LLM calls; the
      TTLs decide staleness, not this cadence.

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
    scheduler.add_job(
        _run_evaluate_scenario_monitors_job,
        trigger=IntervalTrigger(minutes=settings.watchdog_poll_interval_minutes),
        args=(container, settings),
        id=_EVALUATE_SCENARIO_MONITORS_JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    if settings.news_analysis_enabled:
        scheduler.add_job(
            _run_analyze_pending_news_job,
            trigger=IntervalTrigger(minutes=settings.news_analysis_poll_interval_minutes),
            args=(container, settings),
            id=_ANALYZE_PENDING_NEWS_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "analyze-pending-news job scheduled every %d minute(s)",
            settings.news_analysis_poll_interval_minutes,
        )
    else:
        logger.warning(
            "analyze-pending-news job is DISABLED (NEWS_ANALYSIS_ENABLED=false): ingested news "
            "will stay 'pending' until POST /api/v1/news/analyze-pending is called on demand."
        )
    if settings.news_sentiment_enabled:
        scheduler.add_job(
            _run_score_news_sentiment_job,
            trigger=IntervalTrigger(minutes=settings.news_sentiment_poll_interval_minutes),
            args=(container, settings),
            id=_SCORE_NEWS_SENTIMENT_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "score-news-sentiment job scheduled every %d minute(s), %d article(s) per tick",
            settings.news_sentiment_poll_interval_minutes,
            settings.news_sentiment_batch_limit,
        )
    else:
        logger.warning(
            "score-news-sentiment job is DISABLED (NEWS_SENTIMENT_ENABLED=false): news items "
            "will keep sentiment_score = NULL and render as 'unclassified' in the UI."
        )
    if settings.analysis_refresh_enabled:
        scheduler.add_job(
            _run_refresh_tracked_analysis_job,
            trigger=IntervalTrigger(minutes=settings.analysis_refresh_poll_interval_minutes),
            args=(container, settings),
            id=_REFRESH_ANALYSIS_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "analysis-refresh job scheduled every %d minute(s) for locales %s",
            settings.analysis_refresh_poll_interval_minutes,
            settings.analysis_refresh_locales,
        )
    else:
        logger.warning(
            "analysis-refresh job is DISABLED (ANALYSIS_REFRESH_ENABLED=false): shared analysis "
            "will only be regenerated when a user request finds it stale, so that request pays "
            "the full pipeline latency inline."
        )
    if settings.sentinel_alerts_enabled:
        scheduler.add_job(
            _run_sentinel_scan_job,
            trigger=IntervalTrigger(minutes=settings.sentinel_poll_interval_minutes),
            args=(container, settings),
            id=_SENTINEL_SCAN_JOB_ID,
            replace_existing=True,
            max_instances=1,
        )
        logger.info(
            "sentinel-news-scan job scheduled every %d minute(s) "
            "(importance >= %.2f, max %d alert(s) per run)",
            settings.sentinel_poll_interval_minutes,
            settings.sentinel_importance_threshold,
            settings.sentinel_max_alerts_per_run,
        )
    else:
        logger.warning(
            "sentinel-news-scan job is DISABLED (SENTINEL_ALERTS_ENABLED=false): important news "
            "will NOT be pushed to Telegram automatically. POST /event-intelligence/demo and "
            "POST /telegram/send-test-news still work on demand."
        )
    return scheduler
