from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RequestIDMiddleware, unhandled_exception_handler
from app.api.v1.routers import (
    briefing_export_router,
    briefings_router,
    chat_router,
    consequence_chains_router,
    fundamentals_router,
    health_router,
    instruments_router,
    macro_router,
    news_router,
    quant_router,
    reviews_router,
    scenarios_router,
    signals_router,
    telegram_router,
    watchdog_router,
    watchlists_router,
)
from app.core.config import get_settings
from app.core.di import get_container
from app.core.logging import configure_logging
from app.infrastructure.scheduling import build_watchdog_scheduler
from app.infrastructure.telegram import register_telegram_webhook


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()

    # Watchdog/Notifier scheduled jobs (issue #10) — started on boot, shut down on exit so
    # no background task is left dangling. Scan/job logic itself lives in
    # `infrastructure/scheduling`; this is deliberately just start/stop wiring.
    scheduler = build_watchdog_scheduler(get_container(), settings)
    scheduler.start()

    # Telegram webhook registration (issue #14) — best-effort, never blocks boot. Only
    # attempted when both a bot token and a public webhook URL are configured; see
    # `register_telegram_webhook`'s docstring for why this can't be live-verified in a
    # sandbox without a real bot token and a publicly reachable HTTPS URL.
    if settings.telegram_bot_token and settings.telegram_webhook_url:
        await register_telegram_webhook(
            bot_token=settings.telegram_bot_token,
            webhook_url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


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
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health_router)
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(instruments_router, prefix="/api/v1")
    app.include_router(news_router, prefix="/api/v1")
    app.include_router(quant_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(watchlists_router, prefix="/api/v1")
    app.include_router(briefings_router, prefix="/api/v1")
    app.include_router(briefing_export_router, prefix="/api/v1")
    app.include_router(consequence_chains_router, prefix="/api/v1")
    app.include_router(scenarios_router, prefix="/api/v1")
    app.include_router(watchdog_router, prefix="/api/v1")
    app.include_router(macro_router, prefix="/api/v1")
    app.include_router(fundamentals_router, prefix="/api/v1")
    app.include_router(telegram_router, prefix="/api/v1")

    return app


app = create_app()
