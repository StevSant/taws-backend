import logging

from app.domain.briefing.ports import BriefingRepository
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.telegram.briefing_command import BriefingCommand
from app.infrastructure.telegram.format_briefing_reply import format_briefing_reply
from app.infrastructure.telegram.resolve_linked_user_id import resolve_linked_user_id
from app.infrastructure.telegram.unlinked_account_message import UNLINKED_ACCOUNT_MESSAGE

logger = logging.getLogger(__name__)

_NO_WATCHLIST_MESSAGE = (
    "You don't have any watchlists yet. Create one in the TAWS app, then try /briefing again."
)


class BriefingCommandHandler:
    """Handles `/briefing` (issue #19): resolves the linked user, picks a watchlist,
    and replies with that watchlist's latest `Briefing` executive summary.

    Lives in `infrastructure/telegram/` rather than `application/telegram/use_cases/`
    (unlike `LinkTelegramAccount`) on purpose: this class's job is "fetch via domain
    ports, then format Telegram-specific (HTML `parse_mode`) markup and deliver it" —
    exactly the shape `TelegramNotificationChannel` already establishes for Watchdog
    alerts (resolve recipient -> format -> send, all in one infrastructure-layer
    class, constructor-injected with ports only, no domain/application object
    involved). Keeping Telegram markup/formatting out of `application/` is also
    explicit issue #19 guidance. Not a `NotificationChannel` port implementation
    itself — same "single plausible adapter, no real swap point" reasoning
    `ScenarioSimulationRunner`'s docstring gives for not having a port of its own.

    T2 scope decision — watchlist selection: a linked user may own several
    watchlists, and `/briefing` takes no argument to disambiguate. Rather than
    requiring exactly one (too restrictive) or a stateful multi-turn "which one?"
    exchange (this stateless webhook has no session model for that), this defaults to
    the user's MOST RECENTLY CREATED watchlist — the one they're most likely still
    actively tracking. A `/briefing <name>` variant is the natural follow-up if this
    default proves wrong in practice.
    """

    def __init__(
        self,
        link_repository: TelegramLinkRepository,
        watchlist_repository: WatchlistRepository,
        briefing_repository: BriefingRepository,
        messenger: TelegramMessenger,
        frontend_base_url: str,
    ) -> None:
        self._link_repository = link_repository
        self._watchlist_repository = watchlist_repository
        self._briefing_repository = briefing_repository
        self._messenger = messenger
        self._frontend_base_url = frontend_base_url

    async def handle(self, command: BriefingCommand) -> None:
        user_id = await resolve_linked_user_id(self._link_repository, command.chat_id)
        if user_id is None:
            await self._messenger.send_text(command.chat_id, UNLINKED_ACCOUNT_MESSAGE)
            return

        watchlists = await self._watchlist_repository.list_for_user(user_id)
        if not watchlists:
            await self._messenger.send_text(command.chat_id, _NO_WATCHLIST_MESSAGE)
            return

        watchlist = max(watchlists, key=lambda w: w.created_at)
        briefing = await self._briefing_repository.get_latest_for_watchlist(watchlist.id)
        if briefing is None:
            await self._messenger.send_text(command.chat_id, _no_briefing_message(watchlist.name))
            return

        await self._messenger.send_text(
            command.chat_id,
            format_briefing_reply(briefing, watchlist, self._frontend_base_url),
            parse_mode="HTML",
        )


def _no_briefing_message(watchlist_name: str) -> str:
    return f"No briefing yet for '{watchlist_name}'. Generate one from the TAWS app first."
