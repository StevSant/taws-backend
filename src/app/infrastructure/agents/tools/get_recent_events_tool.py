from langchain_core.tools import StructuredTool

from app.domain.event_intelligence.ports import EventRepositoryPort


def build_get_recent_events_tool(
    event_repository: EventRepositoryPort,
) -> StructuredTool:
    """Build a LangChain tool that retrieves recent analyzed news events.

    Gives the advisor visibility into events the Event Intelligence pipeline
    has processed — importance scores, affected sectors/assets, and suggested
    follow-up questions.
    """

    async def _run() -> str:
        events = await event_repository.list_all()
        if not events:
            return "No recent news events have been analyzed."
        parts: list[str] = []
        for event in reversed(events[-10:]):
            parts.append(
                f"- [{event.analyzed_at.strftime('%Y-%m-%d %H:%M UTC')}] "
                f"{event.original.title} (importance={event.importance:.2f}, "
                f"confidence={event.confidence:.2f})"
            )
            if event.summary:
                parts.append(f"  Summary: {event.summary}")
            if event.affected_sectors:
                parts.append(f"  Sectors: {', '.join(event.affected_sectors)}")
            if event.affected_assets:
                parts.append(f"  Assets: {', '.join(event.affected_assets)}")
            if event.suggested_questions:
                parts.append(f"  Follow-up: {' | '.join(event.suggested_questions)}")
        return "\n".join(parts)

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_recent_events",
        description=(
            "Retrieve the most recent news events analyzed by the Event Intelligence "
            "pipeline, including importance scores, affected sectors, and suggested "
            "follow-up questions. Use this to ground answers in real analyzed events "
            "rather than relying on general knowledge."
        ),
    )
