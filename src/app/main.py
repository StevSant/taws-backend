import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import (
    RequestIDMiddleware,
    duplicate_watchlist_item_handler,
    invalid_watchlist_identifier_handler,
    market_data_unavailable_handler,
    unhandled_exception_handler,
)
from app.api.v1.dependencies import dev_fallback_allowed
from app.api.v1.routers import (
    analysis_router,
    briefing_export_router,
    briefings_router,
    charts_router,
    chat_router,
    consequence_chains_router,
    event_intelligence_router,
    fundamentals_router,
    health_router,
    instruments_router,
    macro_router,
    news_router,
    notes_router,
    profile_router,
    quant_router,
    realtime_ws_router,
    reviews_router,
    scenarios_router,
    sentiment_router,
    signals_router,
    telegram_router,
    watchdog_router,
    watchlists_router,
)
from app.core.config import Settings, get_settings
from app.core.di import get_container
from app.core.logging import configure_logging
from app.domain.market.errors import (
    FundamentalsUnavailableError,
    MacroDataUnavailableError,
    MarketDataUnavailableError,
)
from app.domain.sentiment.errors import FearGreedUnavailableError
from app.domain.watchlist.errors import (
    DuplicateWatchlistItemError,
    InvalidWatchlistIdentifierError,
)
from app.infrastructure.scheduling import build_watchdog_scheduler
from app.infrastructure.telegram import register_telegram_webhook

logger = logging.getLogger(__name__)


def _warn_on_misconfigured_auth(settings: Settings) -> None:
    """Loudly flag, at startup, an auth misconfiguration in a non-dev environment.

    In production/staging a missing `SUPABASE_JWT_SECRET` means `require_current_user`
    fails closed and every protected request is rejected with 401. We log `critical`
    rather than crashing the boot: App Runner injects the secret out-of-band, so a hard
    crash here could crash-loop the service instead of surfacing the problem.
    """
    if dev_fallback_allowed(settings):
        return
    if not settings.supabase_jwt_secret:
        logger.critical(
            "SUPABASE_JWT_SECRET is not set in a non-development environment "
            "(app_env=%s). Authentication is misconfigured: all protected requests "
            "will be rejected with 401.",
            settings.app_env,
        )
    if not settings.telegram_webhook_secret:
        logger.warning(
            "TELEGRAM_WEBHOOK_SECRET is not set in a non-development environment "
            "(app_env=%s). The Telegram webhook will reject all inbound updates with 403.",
            settings.app_env,
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    _warn_on_misconfigured_auth(settings)
    container = get_container()

    # Build the DURABLE agent checkpointer (Postgres) once, before the first chat builds the
    # graph. Self-guarding: it degrades to in-memory and logs (critical outside dev) rather
    # than crashing boot when the DB is configured but unreachable — see
    # `Container.initialize_agent_memory`. Closed again in the finally block below.
    await container.initialize_agent_memory()

    # Load the DB-backed instrument catalog once at startup (issue: Instruments
    # Catalog Slice 1) — MUST happen before any request-path code calls
    # `get_instrument_universe()`, which now only returns this prebuilt singleton
    # and never builds it lazily itself (design decision #1). Wrapped in the same
    # "never crash boot" guard as the news warmup below: if Supabase isn't
    # configured/reachable (e.g. local dev, tests), the app still boots. In that
    # degraded case `get_instrument_universe()` still raises on first use (its
    # contract: "built or not", never a silent empty catalog) — but at least the
    # rest of the app (auth, chat, unrelated routers) keeps working.
    try:
        await container.build_instrument_universe()
    except Exception:
        logger.warning(
            "Instrument universe warmup failed; any endpoint depending on the "
            "instrument catalog will fail until this succeeds.",
            exc_info=True,
        )

    # Preload radar reads so the first browser visit does not pay cold-start DI +
    # fixture assembly on the request path. Run it in the BACKGROUND (unlike the instrument
    # universe above, whose contract requires it be loaded before serving): the news fan-out
    # can be slow, and blocking boot on it delays readiness for no correctness gain — a first
    # /radar load that races the warmup is only slower, never wrong. The handle is cancelled
    # in the finally block if it is still running at shutdown.
    async def _warm_radar() -> None:
        try:
            await container.get_news_provider().fetch_news(since_hours=48, limit=50)
        except Exception:
            logger.warning("Radar warmup failed; first /radar load may be slower.", exc_info=True)

    radar_warmup_task = asyncio.create_task(_warm_radar())

    # Watchdog/Notifier scheduled jobs (issue #10) — started on boot, shut down on exit so
    # no background task is left dangling. Scan/job logic itself lives in
    # `infrastructure/scheduling`; this is deliberately just start/stop wiring.
    scheduler = build_watchdog_scheduler(container, settings)
    scheduler.start()

    # Point Telegram at THIS deployment's shared webhook. Load-bearing, not a nicety:
    # without this `setWebhook` call Telegram has nowhere to POST updates, so `/start
    # <token>` never reaches `LinkTelegramAccount` and the `telegram_links` table stays
    # permanently empty — and every command handler (/briefing, /signal, /simular,
    # /impact, chat) plus `TelegramNotificationChannel` resolves its recipient THROUGH
    # that table, so the entire Telegram surface silently does nothing. Best-effort by
    # design: `register_telegram_webhook` swallows its own failures so a sandbox without
    # a reachable HTTPS URL still boots.
    if settings.telegram_bot_token and settings.telegram_webhook_url:
        await register_telegram_webhook(
            bot_token=settings.telegram_bot_token,
            webhook_url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
    else:
        logger.warning(
            "TELEGRAM_BOT_TOKEN and/or TELEGRAM_WEBHOOK_URL are not set; the Telegram "
            "webhook was not registered. Account linking and alert delivery are disabled."
        )

    try:
        yield
    finally:
        if not radar_warmup_task.done():
            radar_warmup_task.cancel()
            with suppress(asyncio.CancelledError):
                await radar_warmup_task
        scheduler.shutdown(wait=False)
        await container.aclose_agent_memory()
        await container.aclose_http_client()


def create_app() -> FastAPI:
    """Application factory: configures logging, CORS, middleware, and routers."""
    settings = get_settings()

    app = FastAPI(title="TAWS Backend", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)
    # Watchlist domain errors → meaningful HTTP status (issue #22); the catch-all stays
    # last as the 500 backstop for everything else.
    app.add_exception_handler(DuplicateWatchlistItemError, duplicate_watchlist_item_handler)
    app.add_exception_handler(InvalidWatchlistIdentifierError, invalid_watchlist_identifier_handler)
    # Every "we have no real data" error maps to the same 503 — never a 200 with a fake number.
    app.add_exception_handler(MarketDataUnavailableError, market_data_unavailable_handler)
    app.add_exception_handler(MacroDataUnavailableError, market_data_unavailable_handler)
    app.add_exception_handler(FundamentalsUnavailableError, market_data_unavailable_handler)
    app.add_exception_handler(FearGreedUnavailableError, market_data_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router)
    app.include_router(charts_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(realtime_ws_router, prefix="/api/v1")
    app.include_router(instruments_router, prefix="/api/v1")
    app.include_router(news_router, prefix="/api/v1")
    app.include_router(quant_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(watchlists_router, prefix="/api/v1")
    app.include_router(notes_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(briefings_router, prefix="/api/v1")
    app.include_router(briefing_export_router, prefix="/api/v1")
    app.include_router(consequence_chains_router, prefix="/api/v1")
    app.include_router(scenarios_router, prefix="/api/v1")
    app.include_router(watchdog_router, prefix="/api/v1")
    app.include_router(macro_router, prefix="/api/v1")
    app.include_router(fundamentals_router, prefix="/api/v1")
    app.include_router(telegram_router, prefix="/api/v1")
    app.include_router(sentiment_router, prefix="/api/v1")
    app.include_router(event_intelligence_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")

    return app


app = create_app()
