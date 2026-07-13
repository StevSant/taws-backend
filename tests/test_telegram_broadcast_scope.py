"""Who is allowed to trigger a Telegram push, and who receives it.

Two things this pins down, both found in review of the shared-bot PR:

1. `POST /event-intelligence/demo` was anonymous while broadcasting to EVERY linked chat.
   It takes an attacker-chosen title/description/content and, with `force_notify`, pushes it
   under the official bot's identity to every user. It must require authentication.

2. `POST /telegram/send-test-news` answers "is MY Telegram wiring working?" but delivered to
   `list_all()` — so one user's test button wrote into every other user's chat. It must
   deliver to the caller's own chat and nobody else's.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_telegram_link_repository,
    get_telegram_messenger,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser
from app.core.config import get_settings
from app.core.di import get_container
from app.domain.telegram.entities import TelegramLink
from app.domain.telegram.ports import TelegramLinkRepository, TelegramMessenger
from app.main import create_app

_CALLER_ID = "11111111-1111-1111-1111-111111111111"
_CALLER_CHAT = "1001"
_OTHER_CHAT = "2002"


class FakeLinkRepository(TelegramLinkRepository):
    """Two linked users: the caller, and somebody else who must not be written to."""

    async def get_by_user_id(self, user_id: str) -> TelegramLink | None:
        if user_id != _CALLER_ID:
            return None
        return TelegramLink(user_id=_CALLER_ID, chat_id=_CALLER_CHAT, linked_at=datetime.now(UTC))

    async def get_by_chat_id(self, chat_id: str) -> TelegramLink | None:
        return None

    async def list_all(self) -> list[TelegramLink]:
        now = datetime.now(UTC)
        return [
            TelegramLink(user_id=_CALLER_ID, chat_id=_CALLER_CHAT, linked_at=now),
            TelegramLink(user_id="other-user", chat_id=_OTHER_CHAT, linked_at=now),
        ]

    async def link(self, link: TelegramLink) -> TelegramLink:
        raise NotImplementedError

    async def unlink(self, user_id: str) -> None:
        raise NotImplementedError


class RecordingMessenger(TelegramMessenger):
    def __init__(self) -> None:
        self.chat_ids: list[str] = []

    async def send_text(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> None:
        self.chat_ids.append(chat_id)


@pytest.fixture
def messenger() -> RecordingMessenger:
    return RecordingMessenger()


@pytest.fixture
def client(messenger: RecordingMessenger, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A production-like app: `app_env=production` so `require_current_user` fails closed.

    Without this the default `app_env=development` lets `dev_fallback_allowed` authenticate
    an anonymous request as the fake `DEV_FALLBACK_USER`, and the anonymous case below would
    pass for the wrong reason — it would never reach the 401 it is meant to prove.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-not-a-real-one")
    get_settings.cache_clear()
    get_container.cache_clear()

    app = create_app()
    app.dependency_overrides[get_telegram_link_repository] = FakeLinkRepository
    app.dependency_overrides[get_telegram_messenger] = lambda: messenger
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_container.cache_clear()


def _authenticate(client: TestClient) -> None:
    client.app.dependency_overrides[require_current_user] = lambda: CurrentUser(  # pyright: ignore[reportAttributeAccessIssue, reportCallIssue]
        id=_CALLER_ID, email="caller@example.com"
    )


def test_demo_event_rejects_anonymous_callers(
    client: TestClient, messenger: RecordingMessenger
) -> None:
    """Anonymous mass-message vector: no auth, no broadcast."""
    response = client.post(
        "/api/v1/event-intelligence/demo",
        json={
            "title": "URGENT: verify your account at http://evil.example",
            "description": "d",
            "content": "c",
            "source": "s",
            "force_notify": True,
        },
    )

    assert response.status_code in (401, 403), (
        f"anonymous caller reached the broadcast (got {response.status_code})"
    )
    assert messenger.chat_ids == [], "an anonymous request pushed a message to Telegram"


def test_send_test_news_delivers_only_to_the_caller(
    client: TestClient, messenger: RecordingMessenger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller's test button must not write into anyone else's chat."""
    _authenticate(client)

    response = client.post("/api/v1/telegram/send-test-news")

    # The news provider may legitimately have nothing to send (400) -- what must never happen,
    # either way, is a message landing in a chat that isn't the caller's.
    assert _OTHER_CHAT not in messenger.chat_ids, (
        f"send-test-news wrote into another user's chat: {messenger.chat_ids}"
    )
    if response.status_code == 200:
        assert messenger.chat_ids == [_CALLER_CHAT]
