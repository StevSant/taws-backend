import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    get_process_incoming_event_use_case,
    get_telegram_messenger,
)
from app.api.v1.schemas import EnrichedEventResponse, EventIntelligenceDemoRequest
from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.domain.event_intelligence.entities import NewsEvent
from app.domain.telegram.ports import TelegramMessenger
from app.infrastructure.telegram.format_event_alert import format_event_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/event-intelligence", tags=["event-intelligence"])


@router.post("/demo", status_code=status.HTTP_201_CREATED)
async def demo_analyze_event(
    payload: EventIntelligenceDemoRequest,
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
    messenger: Annotated[TelegramMessenger | None, Depends(get_telegram_messenger)],
) -> EnrichedEventResponse:
    """Inject a news event manually and run it through the full Sentinel pipeline.

    The event is analyzed by Gemini (or fallback), stored in the in-memory
    repository, and the enriched result is returned. If `telegram_chat_id` was
    provided and the event is important (`should_notify`), a notification is
    sent to that Telegram chat.
    """
    news_event = NewsEvent(
        title=payload.title,
        description=payload.description,
        content=payload.content,
        source=payload.source,
    )
    enriched = await use_case.execute(news_event)

    if enriched.should_notify and payload.telegram_chat_id and messenger is not None:
        try:
            text = format_event_alert(enriched)
            await messenger.send_text(payload.telegram_chat_id, text, parse_mode="HTML")
        except Exception:
            logger.exception(
                "Failed to send Telegram alert for event %s to chat %s",
                enriched.id,
                payload.telegram_chat_id,
            )

    return EnrichedEventResponse.model_validate(enriched)


@router.get("/events")
async def list_events(
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
) -> list[EnrichedEventResponse]:
    """Return all events that have been processed by the Sentinel pipeline."""
    events = await use_case._repository.list_all()
    return [EnrichedEventResponse.model_validate(e) for e in events]
