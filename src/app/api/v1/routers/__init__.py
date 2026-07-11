from app.api.v1.routers.chat import router as chat_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.instruments import router as instruments_router
from app.api.v1.routers.news import router as news_router
from app.api.v1.routers.watchlists import router as watchlists_router

__all__ = [
    "chat_router",
    "health_router",
    "instruments_router",
    "news_router",
    "watchlists_router",
]
