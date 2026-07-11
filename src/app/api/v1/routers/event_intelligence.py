from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import get_process_incoming_event_use_case
from app.api.v1.schemas import EnrichedEventResponse, EventIntelligenceDemoRequest
from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.domain.event_intelligence.entities import NewsEvent

router = APIRouter(prefix="/event-intelligence", tags=["event-intelligence"])


@router.post("/demo", status_code=status.HTTP_201_CREATED)
async def demo_analyze_event(
    payload: EventIntelligenceDemoRequest,
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
) -> EnrichedEventResponse:
    """Inject a news event manually and run it through the full Sentinel pipeline.

    The event is analyzed by Gemini (or fallback), stored in the in-memory
    repository, and the enriched result is returned.
    """
    news_event = NewsEvent(
        title=payload.title,
        description=payload.description,
        content=payload.content,
        source=payload.source,
    )
    enriched = await use_case.execute(news_event)
    return EnrichedEventResponse.model_validate(enriched)


@router.get("/events")
async def list_events(
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
) -> list[EnrichedEventResponse]:
    """Return all events that have been processed by the Sentinel pipeline."""
    events = await use_case._repository.list_all()
    return [EnrichedEventResponse.model_validate(e) for e in events]
