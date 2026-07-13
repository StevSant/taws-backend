import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    get_process_incoming_event_use_case,
    get_user_bot_repository,
)
from app.api.v1.schemas import EnrichedEventResponse, EventIntelligenceDemoRequest
from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.domain.event_intelligence.entities import NewsEvent
from app.domain.telegram.ports import UserBotRepository
from app.infrastructure.telegram import TelegramBotClient
from app.infrastructure.telegram.format_event_alert import format_event_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/event-intelligence", tags=["event-intelligence"])


@router.post("/demo", status_code=status.HTTP_201_CREATED)
async def demo_analyze_event(
    payload: EventIntelligenceDemoRequest,
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
    bot_repository: Annotated[UserBotRepository, Depends(get_user_bot_repository)],
) -> EnrichedEventResponse:
    """Inject a news event manually and run it through the full Sentinel pipeline.

    The event is analyzed by Gemini (or fallback), stored in the in-memory
    repository, and the enriched result is returned. If the event is important
    (`should_notify`), a notification is sent to ALL registered user bots.
    """
    news_event = NewsEvent(
        title=payload.title,
        description=payload.description,
        content=payload.content,
        source=payload.source,
    )
    enriched = await use_case.execute(news_event)

    should_alert = enriched.should_notify or payload.force_notify
    if should_alert:
        text = format_event_alert(enriched)
        bots = await bot_repository.get_all()
        for bot in bots:
            try:
                client = TelegramBotClient(bot_token=bot.bot_token)
                await client.send_text(bot.chat_id, text, parse_mode="HTML")
            except Exception:
                logger.exception(
                    "Failed to send event alert via bot %s for chat %s",
                    bot.bot_username,
                    bot.chat_id,
                )

    return EnrichedEventResponse.model_validate(enriched)


@router.get("/events")
async def list_events(
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
) -> list[EnrichedEventResponse]:
    """Return all events that have been processed by the Sentinel pipeline."""
    events = await use_case._repository.list_all()
    return [EnrichedEventResponse.model_validate(e) for e in events]
