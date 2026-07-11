from app.api.v1.routers.briefing_export import router as briefing_export_router
from app.api.v1.routers.briefings import router as briefings_router
from app.api.v1.routers.chat import router as chat_router
from app.api.v1.routers.consequence_chains import router as consequence_chains_router
from app.api.v1.routers.event_intelligence import router as event_intelligence_router
from app.api.v1.routers.fundamentals import router as fundamentals_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.instruments import router as instruments_router
from app.api.v1.routers.macro import router as macro_router
from app.api.v1.routers.news import router as news_router
from app.api.v1.routers.quant import router as quant_router
from app.api.v1.routers.reviews import router as reviews_router
from app.api.v1.routers.scenarios import router as scenarios_router
from app.api.v1.routers.sentiment import router as sentiment_router
from app.api.v1.routers.signals import router as signals_router
from app.api.v1.routers.telegram import router as telegram_router
from app.api.v1.routers.watchdog import router as watchdog_router
from app.api.v1.routers.watchlists import router as watchlists_router

__all__ = [
    "briefing_export_router",
    "briefings_router",
    "chat_router",
    "consequence_chains_router",
    "event_intelligence_router",
    "fundamentals_router",
    "health_router",
    "instruments_router",
    "macro_router",
    "news_router",
    "quant_router",
    "reviews_router",
    "scenarios_router",
    "sentiment_router",
    "signals_router",
    "telegram_router",
    "watchdog_router",
    "watchlists_router",
]
