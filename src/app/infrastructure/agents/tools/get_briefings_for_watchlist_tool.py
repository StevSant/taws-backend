from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository


class _GetBriefingsForWatchlistArgs(BaseModel):
    watchlist_id: str = Field(description="The watchlist id to look up persisted briefings for.")


def build_get_briefings_for_watchlist_tool(
    briefing_repository: BriefingRepository,
) -> StructuredTool:
    """Build a LangChain tool grounding the Advisor's answers in persisted `Briefing`s.

    Only useful when the user supplies a watchlist id in the chat message itself — the
    chat layer doesn't carry a `user_id`/watchlist context today (`ChatRequest` only has
    `thread_id` + `message`), so there's no way to resolve "the user's watchlists" from a
    thread alone. Documented as a known gap for a future chat-auth issue, not fixed here.
    """

    async def _run(watchlist_id: str) -> str:
        briefings = await briefing_repository.list_for_watchlist(watchlist_id)
        if not briefings:
            return f"No persisted briefings found for watchlist {watchlist_id!r}."
        return "\n".join(_format_briefing(briefing) for briefing in briefings)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_briefings_for_watchlist",
        description=(
            "Look up persisted Advisor briefings (summary + linked signal ids) for one "
            "watchlist id. Use this when the user asks about a specific watchlist by id."
        ),
        args_schema=_GetBriefingsForWatchlistArgs,
    )


def _format_briefing(briefing: Briefing) -> str:
    return (
        f"- [{briefing.created_at.date().isoformat()}] {briefing.summary} "
        f"(linked_signal_ids={briefing.linked_signal_ids})"
    )
