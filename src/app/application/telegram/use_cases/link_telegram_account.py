import logging

from app.domain.telegram.entities import TelegramLink
from app.domain.telegram.ports import (
    TelegramLinkRepository,
    TelegramLinkTokenRepository,
    TelegramMessenger,
)

logger = logging.getLogger(__name__)

_CONFIRMATION_MESSAGE = "Linked! You'll receive alerts here."
_INVALID_TOKEN_MESSAGE = (
    "This link is invalid or has expired. Generate a new one from the TAWS app and try again."
)


class LinkTelegramAccount:
    """Completes the `/start <token>` deep-link flow (issue #14): validates and consumes
    the pending token, persists the `user_id` <-> `chat_id` mapping, and confirms back to
    the user over Telegram.

    Invoked by the webhook router (`api/v1/routers/telegram.py`) once it has parsed a
    `/start <token>` command out of the raw Telegram `Update` payload. Kept as an
    application use case (not inline in the router) because it's real orchestration logic
    across two ports plus a user-facing confirmation — not a thin CRUD passthrough like the
    watchlist endpoints.
    """

    def __init__(
        self,
        token_repository: TelegramLinkTokenRepository,
        link_repository: TelegramLinkRepository,
        messenger: TelegramMessenger,
    ) -> None:
        self._token_repository = token_repository
        self._link_repository = link_repository
        self._messenger = messenger

    async def execute(self, token: str, chat_id: str) -> bool:
        """Returns `True` if `token` was valid and the chat is now linked, `False`
        otherwise.

        Only the confirmation-message send is guarded here: `_try_send`'s failure is
        logged, not propagated, since a failed confirmation must never undo an
        already-persisted link. `consume()` and `link()` above it are deliberately left
        unguarded — a DB/network failure there is a real error, not a "nothing to do"
        case, and this use case has no way to know whether the caller can safely retry.
        The webhook router (`api/v1/routers/telegram.py`) is the one that decides how to
        keep its own "always ack 200 to Telegram" contract around that, since it's a
        webhook-transport concern, not a domain one — see its docstring."""
        consumed = await self._token_repository.consume(token)
        if consumed is None:
            await self._try_send(chat_id, _INVALID_TOKEN_MESSAGE)
            return False

        await self._link_repository.link(TelegramLink(user_id=consumed.user_id, chat_id=chat_id))
        await self._try_send(chat_id, _CONFIRMATION_MESSAGE)
        return True

    async def _try_send(self, chat_id: str, text: str) -> None:
        try:
            await self._messenger.send_text(chat_id, text)
        except Exception:  # noqa: BLE001 — a failed confirmation must never break linking
            logger.exception("Failed to send Telegram confirmation message to chat_id=%s", chat_id)
