import logging

from app.domain.market.ports import InstrumentUniverse
from app.domain.signals.ports import SignalRepository
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.infrastructure.telegram.format_signal_reply import format_signal_reply
from app.infrastructure.telegram.resolve_linked_user_id import resolve_linked_user_id
from app.infrastructure.telegram.signal_command import SignalCommand
from app.infrastructure.telegram.unlinked_account_message import UNLINKED_ACCOUNT_MESSAGE

logger = logging.getLogger(__name__)


class SignalCommandHandler:
    """Handles `/signal <TICKER>` (issue #19): resolves the linked user (`Signal`s
    aren't per-user data — see `SignalRepository`'s docstring — but issue #19 requires
    every new command to gate on a linked account, same as `/briefing`/`/simular`),
    validates the ticker against the curated `InstrumentUniverse`, and replies with
    the most recent `Signal` recorded for that instrument.

    Same "infrastructure, not application" placement rationale as
    `BriefingCommandHandler` — see its docstring.
    """

    def __init__(
        self,
        link_repository: TelegramLinkRepository,
        instrument_universe: InstrumentUniverse,
        signal_repository: SignalRepository,
        messenger: TelegramMessenger,
    ) -> None:
        self._link_repository = link_repository
        self._instrument_universe = instrument_universe
        self._signal_repository = signal_repository
        self._messenger = messenger

    async def handle(self, command: SignalCommand) -> None:
        user_id = await resolve_linked_user_id(self._link_repository, command.chat_id)
        if user_id is None:
            await self._messenger.send_text(command.chat_id, UNLINKED_ACCOUNT_MESSAGE)
            return

        instrument = self._instrument_universe.by_symbol(command.ticker)
        if instrument is None:
            await self._messenger.send_text(
                command.chat_id, _unknown_ticker_message(command.ticker)
            )
            return

        signals = await self._signal_repository.list_for_instrument(instrument.symbol)
        if not signals:
            await self._messenger.send_text(command.chat_id, _no_signal_message(instrument.symbol))
            return

        latest = max(signals, key=lambda signal: signal.created_at)
        await self._messenger.send_text(
            command.chat_id, format_signal_reply(latest), parse_mode="HTML"
        )


def _unknown_ticker_message(ticker: str) -> str:
    return (
        f"'{ticker}' isn't a recognized instrument. Check the ticker and try again, "
        "e.g. /signal AAPL."
    )


def _no_signal_message(symbol: str) -> str:
    return f"No signals recorded yet for {symbol}."
