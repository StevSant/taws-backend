from app.infrastructure.persistence.supabase_briefing_repository import (
    SupabaseBriefingRepository,
)
from app.infrastructure.persistence.supabase_conversation_repository import (
    SupabaseConversationRepository,
)
from app.infrastructure.persistence.supabase_news_item_repository import (
    SupabaseNewsItemRepository,
)
from app.infrastructure.persistence.supabase_note_repository import SupabaseNoteRepository
from app.infrastructure.persistence.supabase_scenario_repository import (
    SupabaseScenarioRepository,
)
from app.infrastructure.persistence.supabase_sentiment_repository import (
    SupabaseSentimentRepository,
)
from app.infrastructure.persistence.supabase_signal_repository import SupabaseSignalRepository
from app.infrastructure.persistence.supabase_telegram_link_repository import (
    SupabaseTelegramLinkRepository,
)
from app.infrastructure.persistence.supabase_telegram_link_token_repository import (
    SupabaseTelegramLinkTokenRepository,
)
from app.infrastructure.persistence.supabase_user_bot_repository import SupabaseUserBotRepository
from app.infrastructure.persistence.supabase_watchlist_repository import (
    SupabaseWatchlistRepository,
)

__all__ = [
    "SupabaseBriefingRepository",
    "SupabaseConversationRepository",
    "SupabaseNewsItemRepository",
    "SupabaseNoteRepository",
    "SupabaseScenarioRepository",
    "SupabaseSentimentRepository",
    "SupabaseSignalRepository",
    "SupabaseTelegramLinkRepository",
    "SupabaseTelegramLinkTokenRepository",
    "SupabaseUserBotRepository",
    "SupabaseWatchlistRepository",
]
