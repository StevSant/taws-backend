from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RequestIDMiddleware, unhandled_exception_handler
from app.api.v1.routers import (
    briefings_router,
    chat_router,
    health_router,
    instruments_router,
    news_router,
    quant_router,
    reviews_router,
    signals_router,
    watchlists_router,
)
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


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

    return app


app = create_app()
