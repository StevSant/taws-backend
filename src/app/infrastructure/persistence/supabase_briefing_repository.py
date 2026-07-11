from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.review.entities import ReviewedEntityType, ReviewState
from app.infrastructure.persistence.briefing_row_mapper import briefing_from_row
from app.infrastructure.persistence.review_state_row_mapper import (
    review_state_from_row,
    review_state_to_row,
)
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache

_BRIEFINGS_TABLE = "briefings"
_REVIEW_STATES_TABLE = "review_states"


class SupabaseBriefingRepository(BriefingRepository):
    """BriefingRepository adapter backed by Supabase Postgres via `supabase-py`.

    Written by the Advisor agent (issue #3). See
    `backend/migrations/0001_watchlists_signals_briefings.sql` for the `briefings` and
    `review_states` schema and RLS policies.
    """

    def __init__(self, supabase_url: str | None, supabase_key: str | None) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)

    async def create(self, briefing: Briefing) -> Briefing:
        client = await self._clients.get()
        response = (
            await client.table(_BRIEFINGS_TABLE)
            .insert(
                {
                    "id": briefing.id,
                    "watchlist_id": briefing.watchlist_id,
                    "summary": briefing.summary,
                    "disclaimer": briefing.disclaimer,
                    "linked_signal_ids": briefing.linked_signal_ids,
                    "created_at": briefing.created_at.isoformat(),
                }
            )
            .execute()
        )
        return briefing_from_row(response.data[0])

    async def get(self, briefing_id: str) -> Briefing | None:
        client = await self._clients.get()
        response = await client.table(_BRIEFINGS_TABLE).select("*").eq("id", briefing_id).execute()
        return briefing_from_row(response.data[0]) if response.data else None

    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        client = await self._clients.get()
        response = (
            await client.table(_BRIEFINGS_TABLE)
            .select("*")
            .eq("watchlist_id", watchlist_id)
            .execute()
        )
        return [briefing_from_row(row) for row in response.data]

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        client = await self._clients.get()
        response = (
            await client.table(_REVIEW_STATES_TABLE)
            .insert(review_state_to_row(review_state))
            .execute()
        )
        return review_state_from_row(response.data[0])

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        client = await self._clients.get()
        response = (
            await client.table(_REVIEW_STATES_TABLE)
            .select("*")
            .eq("entity_type", ReviewedEntityType.BRIEFING.value)
            .eq("entity_id", briefing_id)
            .order("created_at")
            .execute()
        )
        return [review_state_from_row(row) for row in response.data]
