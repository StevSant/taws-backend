"""Regression: a user-registered bot must reply through its OWN token.

Bug: every newly registered bot answered as the *main* `.env` bot. `telegram_webhook_for_bot`
built a per-bot `TelegramBotClient` but only used it for `/start` and unknown commands —
`/briefing`, `/signal`, `/simular`, `/impact` and plain chat were dispatched to the cached
`Depends(get_*_command_handler)` singletons, which the `Container` builds once around
`TelegramBotClient(bot_token=settings.telegram_bot_token)`.

A handler replies with `messenger.send_text(command.chat_id, ...)`, so the messenger it holds
is the identity the user sees. And in a private chat a Telegram `chat_id` is the user's account
ID — IDENTICAL across every bot — so the misrouted reply was still delivered; it just surfaced
in the OLD bot's conversation. Hence "interactúo con el bot nuevo y me responde el bot antiguo".

These tests assert the token each reply actually goes out with.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_user_bot_repository
from app.core.config import get_settings
from app.core.di import Container, get_container
from app.domain.telegram.entities import TelegramLink, UserBot
from app.domain.telegram.ports import TelegramLinkRepository, UserBotRepository
from app.infrastructure.telegram import TelegramBotClient
from app.main import create_app

_MAIN_BOT_TOKEN = "111111:MAIN-env-bot-token"
_USER_BOT_TOKEN = "222222:USER-registered-bot-token"
_BOT_ID = "22222222-2222-2222-2222-222222222222"
# In a private chat this is the user's Telegram account ID -- the SAME value for every bot,
# which is exactly why replying with the wrong token still "worked" and hid the bug.
_CHAT_ID = "987654321"

_USER_BOT = UserBot(
    id=_BOT_ID,
    user_id="11111111-1111-1111-1111-111111111111",
    bot_token=_USER_BOT_TOKEN,
    bot_username="ProductionMidas2Bot",
    chat_id=_CHAT_ID,
)


class FakeUserBotRepository(UserBotRepository):
    async def get_by_user_id(self, user_id: str) -> UserBot | None:
        return _USER_BOT if user_id == _USER_BOT.user_id else None

    async def get_by_id(self, bot_id: str) -> UserBot | None:
        return _USER_BOT if bot_id == _BOT_ID else None

    async def get_by_chat_id(self, chat_id: str) -> list[UserBot]:
        return [_USER_BOT] if chat_id == _CHAT_ID else []

    async def get_all(self) -> list[UserBot]:
        return [_USER_BOT]

    async def save(self, bot: UserBot) -> UserBot:
        return _USER_BOT

    async def delete(self, user_id: str) -> None:
        return None


class UnlinkedTelegramLinkRepository(TelegramLinkRepository):
    """No chat is linked, so `/briefing` short-circuits to its "not linked yet" reply.

    Which message comes back doesn't matter here — only which bot it comes FROM. This keeps
    the test off the network while still exercising the real handler.
    """

    async def get_by_chat_id(self, chat_id: str) -> TelegramLink | None:
        return None

    async def get_by_user_id(self, user_id: str) -> TelegramLink | None:
        return None

    async def link(self, user_id: str, chat_id: str) -> TelegramLink:
        raise NotImplementedError

    async def unlink(self, user_id: str) -> None:
        raise NotImplementedError


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture `(bot_token, chat_id)` for every outbound Telegram message, no network."""
    calls: list[tuple[str, str]] = []

    async def fake_send_text(
        self: TelegramBotClient, chat_id: str, text: str, *, parse_mode: str | None = None
    ) -> None:
        calls.append((self._bot.token, chat_id))  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(TelegramBotClient, "send_text", fake_send_text)
    return calls


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App with the main `.env` bot configured — the state that triggered the bug."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _MAIN_BOT_TOKEN)
    monkeypatch.setattr(
        Container, "get_telegram_link_repository", lambda self: UnlinkedTelegramLinkRepository()
    )
    get_settings.cache_clear()
    get_container.cache_clear()

    app = create_app()
    app.dependency_overrides[get_user_bot_repository] = FakeUserBotRepository
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_container.cache_clear()


def _update(text: str) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": int(_CHAT_ID), "type": "private"},
            "text": text,
        },
    }


@pytest.mark.parametrize("text", ["/start", "/unknowncommand", "/briefing"])
def test_user_bot_webhook_replies_with_its_own_token(
    client: TestClient, sent: list[tuple[str, str]], text: str
) -> None:
    """`/briefing` is the regression: it dispatches through a Container-built handler, which
    used to be the cached one bound to the main `.env` bot."""
    response = client.post(f"/api/v1/telegram/webhook/{_BOT_ID}", json=_update(text))

    assert response.status_code == 200
    assert sent, f"{text} produced no reply at all"
    assert all(token == _USER_BOT_TOKEN for token, _ in sent), (
        f"{text} replied with the main .env bot's token instead of the registered bot's: {sent}"
    )


def test_built_handlers_are_bound_to_the_messenger_they_are_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-bot handler replies through the messenger it was handed, and is never the
    cached instance the main `.env` bot replies through."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _MAIN_BOT_TOKEN)
    get_settings.cache_clear()
    container = Container(get_settings())

    user_messenger = TelegramBotClient(bot_token=_USER_BOT_TOKEN)
    user_handler = container.build_briefing_command_handler(user_messenger)
    main_handler = container.get_briefing_command_handler()

    assert user_handler._messenger is user_messenger  # pyright: ignore[reportPrivateUsage]
    assert main_handler is not None
    assert main_handler is not user_handler
    assert main_handler._messenger is not user_messenger  # pyright: ignore[reportPrivateUsage]

    get_settings.cache_clear()
