from app.api.v1.routers.briefings import router as briefings_router
from app.api.v1.routers.chat import router as chat_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.instruments import router as instruments_router
from app.api.v1.routers.news import router as news_router
from app.api.v1.routers.reviews import router as reviews_router
from app.api.v1.routers.signals import router as signals_router
from app.api.v1.routers.watchlists import router as watchlists_router

__all__ = [
    "briefings_router",
    "chat_router",
    "health_router",
    "instruments_router",
    "news_router",
    "reviews_router",
    "signals_router",
    "watchlists_router",
]
