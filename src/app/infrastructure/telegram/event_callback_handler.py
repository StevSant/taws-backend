import logging

from app.application.event_intelligence.use_cases import AnalyzeEventImpact
from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.event_intelligence.ports import EventRepositoryPort
from app.domain.telegram.ports import TelegramMessenger
from app.infrastructure.telegram.chat_message import ChatMessage
from app.infrastructure.telegram.chat_message_handler import ChatMessageHandler
from app.infrastructure.telegram.event_callback import EventCallback
from app.infrastructure.telegram.event_callback_action import EventCallbackAction
from app.infrastructure.telegram.format_impact_reply import format_impact_reply

logger = logging.getLogger(__name__)

_EXPIRED_TOAST = "Esa noticia ya no está disponible."
_FAILURE_TOAST = "No se pudo completar la acción. Inténtalo de nuevo."
_GENERIC_SECTOR = "el mercado en general"


class EventCallbackHandler:
    """Services a tapped inline button on a broadcast news alert.

    Both actions reuse machinery that already existed rather than adding a parallel path:

    - `ASK_QUESTION` re-sends the chosen suggested question through `ChatMessageHandler`, the
      same component that already answers free-text Telegram messages — so a tapped question is
      indistinguishable, downstream, from the user having typed it.
    - `ANALYZE_IMPACT` runs the existing `AnalyzeEventImpact` (Gemini) use case, which is what
      the `/impact <sector>` command already calls. It targets the event's own primary affected
      sector, which is the whole reason a per-event button beats the command: `/impact` operates
      on whatever event happens to be *latest* in the store, whereas this button carries the id
      of the specific article the user is looking at.

    **Always answers the callback.** Telegram spins the button until `answerCallbackQuery`
    arrives and re-delivers the update if it never does, so every path here — including a miss
    and including a failure — acknowledges. A stale button is a routine outcome, not a bug: the
    event store is in-memory, so a restart empties it while the alert (and its buttons) live on
    in the user's chat history forever.
    """

    def __init__(
        self,
        event_repository: EventRepositoryPort,
        analyze_event_impact: AnalyzeEventImpact,
        chat_message_handler: ChatMessageHandler,
        messenger: TelegramMessenger,
    ) -> None:
        self._event_repository = event_repository
        self._analyze_event_impact = analyze_event_impact
        self._chat_message_handler = chat_message_handler
        self._messenger = messenger

    async def handle(self, callback: EventCallback) -> None:
        event = await self._event_repository.get(callback.event_id)
        if event is None:
            await self._messenger.answer_callback(callback.callback_query_id, _EXPIRED_TOAST)
            return

        # Acknowledge BEFORE the slow work: both branches below call an LLM, and Telegram's
        # callback ack has a short deadline — leaving it until afterwards means the button
        # spins for the whole analysis and Telegram re-delivers the update, running it twice.
        await self._messenger.answer_callback(callback.callback_query_id)

        try:
            if callback.action is EventCallbackAction.ASK_QUESTION:
                await self._ask_question(callback, event)
            else:
                await self._analyze_impact(callback, event)
        except Exception:  # noqa: BLE001 — a webhook must never 500 on a tapped button
            logger.exception(
                "Failed to handle %s callback for event %s", callback.action, callback.event_id
            )
            await self._messenger.send_text(callback.chat_id, _FAILURE_TOAST)

    async def _ask_question(self, callback: EventCallback, event: EnrichedEvent) -> None:
        index = callback.question_index
        if index is None or index >= len(event.suggested_questions):
            # The alert was built from a different set of questions than the event now carries
            # — only reachable if the store were mutated under us. Decline quietly.
            logger.warning("Question index %s out of range for event %s", index, callback.event_id)
            return

        question = event.suggested_questions[index]
        await self._chat_message_handler.handle(
            ChatMessage(chat_id=callback.chat_id, text=question)
        )

    async def _analyze_impact(self, callback: EventCallback, event: EnrichedEvent) -> None:
        sector = _primary_sector(event)
        analysis = await self._analyze_event_impact.execute(event, sector)
        await self._messenger.send_text(
            callback.chat_id, format_impact_reply(sector, analysis), parse_mode="HTML"
        )


def _primary_sector(event: EnrichedEvent) -> str:
    """The subject of the impact analysis: the event's headline sector, else its headline
    asset, else the market at large — so the button always has something to analyze even for an
    event the model couldn't attribute to anything specific."""
    if event.affected_sectors:
        return event.affected_sectors[0]
    if event.affected_assets:
        return event.affected_assets[0]
    return _GENERIC_SECTOR
