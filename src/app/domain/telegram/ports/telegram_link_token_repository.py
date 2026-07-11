from abc import ABC, abstractmethod

from app.domain.telegram.entities import TelegramLinkToken


class TelegramLinkTokenRepository(ABC):
    """Port for persisting the short-lived, single-use tokens behind the `/start <token>`
    deep-link flow.

    A DB-backed store (not in-process) on purpose: this backend can run as multiple
    workers, and tokens must survive a restart between "generate token" and "user taps
    the deep link" — see `POST /api/v1/telegram/link-token`.
    """

    @abstractmethod
    async def create(self, token: TelegramLinkToken) -> TelegramLinkToken:
        """Persist a newly generated pending token."""
        raise NotImplementedError

    @abstractmethod
    async def consume(self, token: str) -> TelegramLinkToken | None:
        """Atomically validate and consume a token in one round trip.

        Returns the token (with `consumed_at` now set) if it exists, is unexpired, and
        hasn't already been consumed — otherwise `None`. Must be atomic at the storage
        layer (a single conditional UPDATE, not a read-then-write) so the same token can
        never be consumed twice, even under concurrent webhook deliveries for the same
        Telegram update.
        """
        raise NotImplementedError
