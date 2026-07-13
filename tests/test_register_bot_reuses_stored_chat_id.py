"""Regression: re-registering an already-registered bot must not go through `getUpdates`.

Bug: clicking "Registrar Bot" a second time always failed with "No se encontró ningún
mensaje en el bot". `TelegramBotRegistration._get_chat_id` is the only source of `chat_id`,
but the *first* registration ends in `setWebhook`, and Telegram delivers every pending
update to the webhook — draining the `getUpdates` queue. So the second call found an empty
queue and raised. Worse, `_get_chat_id` calls `deleteWebhook` before it fails, so the failed
retry left the already-working bot with no webhook at all (verified live: `getWebhookInfo`
returned `{"url": "", "pending_update_count": 0}`).

Fix: when the same user re-submits the same `bot_token`, reuse the `chat_id` already stored
(`user_bots.chat_id` is `not null`) and never touch the webhook to read it.
"""

import pytest

from app.domain.telegram.entities import UserBot
from app.domain.telegram.ports import UserBotRepository
from app.infrastructure.telegram import TelegramBotRegistration

_USER_ID = "11111111-1111-1111-1111-111111111111"
_BOT_ID = "22222222-2222-2222-2222-222222222222"
_BOT_TOKEN = "8717249532:AAEIqs9uZs0oVgWzuv_LA7ByWZTdXGfdhKQ"
_BOT_USERNAME = "ProductionMidas2Bot"
_CHAT_ID = "987654321"

_BOTFATHER_TEXT = f"""Done! Congratulations on your new bot.
You will find it at t.me/{_BOT_USERNAME}.

Use this token to access the HTTP API:
{_BOT_TOKEN}
Keep your token secure and store it safely, it can be used by anyone to control your bot.
"""


class FakeUserBotRepository(UserBotRepository):
    """In-memory `UserBotRepository` upserting on `user_id`, like the Supabase adapter."""

    def __init__(self, existing: UserBot | None = None) -> None:
        self.rows: dict[str, UserBot] = {existing.user_id: existing} if existing else {}
        self.deleted: list[str] = []

    async def get_by_user_id(self, user_id: str) -> UserBot | None:
        return self.rows.get(user_id)

    async def get_by_id(self, bot_id: str) -> UserBot | None:
        return next((b for b in self.rows.values() if b.id == bot_id), None)

    async def get_by_chat_id(self, chat_id: str) -> list[UserBot]:
        return [b for b in self.rows.values() if b.chat_id == chat_id]

    async def get_all(self) -> list[UserBot]:
        return list(self.rows.values())

    async def save(self, bot: UserBot) -> UserBot:
        previous = self.rows.get(bot.user_id)
        saved = UserBot(
            id=previous.id if previous else _BOT_ID,
            user_id=bot.user_id,
            bot_token=bot.bot_token,
            bot_username=bot.bot_username,
            chat_id=bot.chat_id,
        )
        self.rows[bot.user_id] = saved
        return saved

    async def delete(self, user_id: str) -> None:
        self.deleted.append(user_id)
        self.rows.pop(user_id, None)


@pytest.fixture
def telegram_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the Telegram API calls the adapter makes, without hitting the network.

    `getUpdates` returns nothing — exactly what Telegram does once a webhook has drained
    the update queue, which is the state a re-registration always starts from.
    """
    calls: list[str] = []

    async def fake_get_chat_id(self: TelegramBotRegistration, bot_token: str) -> str | None:
        calls.append("getUpdates")
        return None

    async def fake_delete_webhook(self: TelegramBotRegistration, bot_token: str) -> None:
        calls.append("deleteWebhook")

    async def fake_set_webhook(self: TelegramBotRegistration, bot_token: str, bot_id: str) -> None:
        calls.append("setWebhook")

    monkeypatch.setattr(TelegramBotRegistration, "_get_chat_id", fake_get_chat_id)
    monkeypatch.setattr(TelegramBotRegistration, "_delete_webhook", fake_delete_webhook)
    monkeypatch.setattr(TelegramBotRegistration, "_set_webhook", fake_set_webhook)
    return calls


async def test_reregistering_same_bot_reuses_stored_chat_id(telegram_calls: list[str]) -> None:
    """The second "Registrar Bot" click succeeds: chat_id comes from the stored row."""
    existing = UserBot(
        id=_BOT_ID,
        user_id=_USER_ID,
        bot_token=_BOT_TOKEN,
        bot_username=_BOT_USERNAME,
        chat_id=_CHAT_ID,
    )
    repository = FakeUserBotRepository(existing)
    registration = TelegramBotRegistration(
        repository=repository, webhook_base_url="https://api.example.com/api/v1/telegram/webhook"
    )

    bot = await registration.register(user_id=_USER_ID, botfather_text=_BOTFATHER_TEXT)

    assert bot.chat_id == _CHAT_ID
    assert bot.id == _BOT_ID
    assert "getUpdates" not in telegram_calls
    assert "deleteWebhook" not in telegram_calls, "a retry must not tear down a live webhook"
    assert "setWebhook" in telegram_calls


async def test_failed_retry_keeps_the_existing_registration(
    monkeypatch: pytest.MonkeyPatch, telegram_calls: list[str]
) -> None:
    """A `setWebhook` failure on a retry must not delete the row that was already working.

    `save` upserts on `user_id`, so on a re-registration the row predates the call — the
    "roll the insert back" compensation only applies to a first registration.
    """

    async def failing_set_webhook(
        self: TelegramBotRegistration, bot_token: str, bot_id: str
    ) -> None:
        raise ValueError("Telegram rechazó el webhook")

    monkeypatch.setattr(TelegramBotRegistration, "_set_webhook", failing_set_webhook)

    existing = UserBot(
        id=_BOT_ID,
        user_id=_USER_ID,
        bot_token=_BOT_TOKEN,
        bot_username=_BOT_USERNAME,
        chat_id=_CHAT_ID,
    )
    repository = FakeUserBotRepository(existing)
    registration = TelegramBotRegistration(
        repository=repository, webhook_base_url="https://api.example.com/api/v1/telegram/webhook"
    )

    with pytest.raises(ValueError, match="rechazó el webhook"):
        await registration.register(user_id=_USER_ID, botfather_text=_BOTFATHER_TEXT)

    assert repository.deleted == []
    assert await repository.get_by_user_id(_USER_ID) == existing


async def test_first_registration_still_requires_a_message(telegram_calls: list[str]) -> None:
    """A bot nobody has registered yet still needs `getUpdates` to discover the chat_id."""
    repository = FakeUserBotRepository()
    registration = TelegramBotRegistration(
        repository=repository, webhook_base_url="https://api.example.com/api/v1/telegram/webhook"
    )

    with pytest.raises(ValueError, match="No se encontró ningún mensaje"):
        await registration.register(user_id=_USER_ID, botfather_text=_BOTFATHER_TEXT)

    assert "getUpdates" in telegram_calls
