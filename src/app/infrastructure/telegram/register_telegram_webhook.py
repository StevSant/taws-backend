import logging

from telegram import Bot

logger = logging.getLogger(__name__)


async def register_telegram_webhook(
    bot_token: str, webhook_url: str, secret_token: str | None
) -> None:
    """Best-effort: register this backend's webhook URL with Telegram's `setWebhook` API,
    called once from `main.py`'s lifespan on boot (only when both `TELEGRAM_BOT_TOKEN` and
    `TELEGRAM_WEBHOOK_URL` are configured).

    Never raises: a sandbox/local-dev environment without a real bot token or a public
    HTTPS URL Telegram can reach would otherwise crash the app on every boot. `secret_token`
    (if set) is echoed back by Telegram on every webhook POST as the
    `X-Telegram-Bot-Api-Secret-Token` header — see `api/v1/routers/telegram.py`'s
    `_verify_telegram_secret` for the corresponding check.

    NOTE: this call cannot be live-verified without a real Telegram bot token and a
    publicly reachable HTTPS URL — neither is available in this sandbox. The webhook
    HANDLER logic itself (`parse_start_command`, `LinkTelegramAccount`) is tested against
    synthetic payloads instead; see the issue #14 implementation report.
    """
    try:
        bot = Bot(token=bot_token)
        await bot.set_webhook(url=webhook_url, secret_token=secret_token or None)
        logger.info("Telegram webhook registered: %s", webhook_url)
    except Exception:  # noqa: BLE001 — webhook registration must never block app startup
        logger.exception("Failed to register Telegram webhook (continuing without it)")
