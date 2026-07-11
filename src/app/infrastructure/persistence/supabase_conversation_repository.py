from app.domain.chat.entities import Conversation
from app.domain.chat.ports import ConversationRepository


class SupabaseConversationRepository(ConversationRepository):
    """ConversationRepository adapter, intended to be backed by Supabase Postgres.

    Stub for the hackathon skeleton: methods currently use an in-process dict so the
    chat endpoint runs end-to-end without external services configured. Replace the
    dict with real `supabase-py` (or SQLAlchemy async) calls against
    `settings.supabase_url` / `settings.supabase_key` when the data layer lands.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key
        self._conversations: dict[str, Conversation] = {}

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    async def save(self, conversation: Conversation) -> None:
        self._conversations[conversation.id] = conversation

    async def list_for_user(self, user_id: str) -> list[Conversation]:
        return [c for c in self._conversations.values() if c.user_id == user_id]
