import logging

from app.application.event_intelligence.use_cases import AnalyzeEventImpact
from app.domain.event_intelligence.ports import EventRepositoryPort
from app.domain.telegram.ports import TelegramMessenger
from app.infrastructure.telegram.format_impact_reply import format_impact_reply
from app.infrastructure.telegram.impact_command import ImpactCommand

logger = logging.getLogger(__name__)

_NO_EVENTS_MESSAGE = (
    "No events have been analyzed yet. Use the TAWS app to inject a news event first."
)
_FAILURE_MESSAGE = (
    "Sorry, the impact analysis failed. Try again later or ask about a different sector."
)


class ImpactCommandHandler:
    """Handles `/impact <sector>`: fetches the latest enriched event from the
    repository and analyzes its impact on the specified sector using Gemini.

    Same infrastructure-layer placement as `BriefingCommandHandler` and
    `SimulateCommandHandler` — see their docstrings for the rationale.
    """

    def __init__(
        self,
        event_repository: EventRepositoryPort,
        analyze_event_impact: AnalyzeEventImpact,
        messenger: TelegramMessenger,
    ) -> None:
        self._event_repository = event_repository
        self._analyze_event_impact = analyze_event_impact
        self._messenger = messenger

    async def handle(self, command: ImpactCommand) -> None:
        events = await self._event_repository.list_all()
        if not events:
            await self._messenger.send_text(command.chat_id, _NO_EVENTS_MESSAGE)
            return

        latest = events[-1]
        try:
            analysis = await self._analyze_event_impact.execute(latest, command.sector)
        except Exception:  # noqa: BLE001 — must never crash the webhook.
            logger.exception(
                "Impact analysis failed for event %s, sector %s, chat_id %s",
                latest.id,
                command.sector,
                command.chat_id,
            )
            await self._messenger.send_text(command.chat_id, _FAILURE_MESSAGE)
            return

        await self._messenger.send_text(
            command.chat_id,
            format_impact_reply(command.sector, analysis),
            parse_mode="HTML",
        )