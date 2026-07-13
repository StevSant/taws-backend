import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    get_event_repository,
    get_process_incoming_event_use_case,
    get_telegram_link_repository,
    get_telegram_messenger,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser, EnrichedEventResponse, EventIntelligenceDemoRequest
from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.core.config import Settings, get_settings
from app.domain.event_intelligence.entities import NewsEvent
from app.domain.event_intelligence.ports import EventRepositoryPort
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.infrastructure.telegram import build_event_alert_buttons, format_event_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/event-intelligence", tags=["event-intelligence"])


@router.post("/demo", status_code=status.HTTP_201_CREATED)
async def demo_analyze_event(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    payload: EventIntelligenceDemoRequest,
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
    link_repository: Annotated[TelegramLinkRepository, Depends(get_telegram_link_repository)],
    messenger: Annotated[TelegramMessenger | None, Depends(get_telegram_messenger)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EnrichedEventResponse:
    """Inject a news event manually and run it through the full Sentinel pipeline.

    The event is analyzed by Gemini (or fallback), stored in the in-memory
    repository, and the enriched result is returned. If the event is important
    (`should_notify`), it is broadcast over the SHARED bot to every chat linked in
    `telegram_links` — i.e. everyone who completed the `/start <token>` deep link.

    Authentication is load-bearing, not boilerplate: this endpoint takes an attacker-chosen
    `title`/`description`/`content` and (with `force_notify`) pushes it, under the identity
    of the official shared bot, to EVERY linked chat. Left anonymous it is a one-request
    mass-message vector into every user's Telegram — `format_event_alert` escapes the text,
    so no markup is injected, but Telegram still auto-links bare URLs in the body. It also
    runs the LLM pipeline per call, so anonymous access is an unmetered spend vector too.
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
        if messenger is None:
            logger.warning(
                "Event alert not delivered: TELEGRAM_BOT_TOKEN is not configured, so there "
                "is no shared bot to broadcast through."
            )
        else:
            text = format_event_alert(enriched)
            buttons = build_event_alert_buttons(enriched, settings.frontend_base_url)
            # Per-recipient guard: one bad chat (bot blocked, chat deleted) must never abort
            # delivery to everyone behind it in the loop.
            for link in await link_repository.list_all():
                try:
                    await messenger.send_text(
                        link.chat_id, text, parse_mode="HTML", buttons=buttons
                    )
                except Exception:
                    logger.exception("Failed to send event alert to chat %s", link.chat_id)

    return EnrichedEventResponse.model_validate(enriched)


@router.get("/events")
async def list_events(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[EventRepositoryPort, Depends(get_event_repository)],
) -> list[EnrichedEventResponse]:
    """Return all events that have been processed by the Sentinel pipeline, newest first.

    Auth-gated like every other endpoint in this router. It previously wasn't — the one
    route here with no `require_current_user` — which left the full Gemini-enriched event
    feed (summaries, importance scores, affected assets, reasoning) readable by anyone who
    could reach the API.

    It also reached into `ProcessIncomingEvent._repository`, a private attribute of a use
    case, to get at the store. The repository is a port; this now injects it directly rather
    than borrowing another object's reference to it.
    """
    events = await repository.list_all()
    return [EnrichedEventResponse.model_validate(event) for event in events]
