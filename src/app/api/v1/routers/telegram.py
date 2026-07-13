import logging
import random
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.middleware.cors_headers import build_cors_headers_for_origin
from app.api.v1.dependencies import (
    dev_fallback_allowed,
    get_bot_registration,
    get_briefing_command_handler,
    get_chat_message_handler,
    get_event_news_provider,
    get_impact_command_handler,
    get_link_telegram_account_use_case,
    get_process_incoming_event_use_case,
    get_signal_command_handler,
    get_simulate_command_handler,
    get_telegram_link_repository,
    get_telegram_link_token_repository,
    get_telegram_messenger,
    get_user_bot_repository,
    require_current_user,
)
from app.api.v1.schemas import (
    CurrentUser,
    RegisterBotRequest,
    RegisterBotResponse,
    SendTestNewsResponse,
    TelegramLinkStatusResponse,
    TelegramLinkTokenResponse,
)
from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.application.telegram.use_cases import LinkTelegramAccount
from app.core.config import Settings, get_settings
from app.core.di import Container, get_container
from app.domain.event_intelligence.ports import NewsProviderPort
from app.domain.telegram.entities import TelegramLinkToken
from app.domain.telegram.ports import (
    BotRegistrationPort,
    TelegramLinkRepository,
    TelegramLinkTokenRepository,
    TelegramMessenger,
    UserBotRepository,
)
from app.infrastructure.telegram import (
    BriefingCommand,
    BriefingCommandHandler,
    ChatMessage,
    ChatMessageHandler,
    ImpactCommand,
    ImpactCommandHandler,
    SignalCommand,
    SignalCommandHandler,
    SimulateCommand,
    SimulateCommandHandler,
    StartCommand,
    TelegramBotClient,
    UnknownCommand,
    format_unknown_command_reply,
    format_welcome_reply,
    parse_telegram_command,
)
from app.infrastructure.telegram.format_event_alert import format_event_alert

logger = logging.getLogger(__name__)

# Emit the "no webhook secret, accepting anonymous POSTs" warning only once per process.
_telegram_secret_warned = False

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/register-bot", status_code=status.HTTP_201_CREATED, response_model=None)
async def register_bot(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    body: RegisterBotRequest,
    registration: Annotated[BotRegistrationPort, Depends(get_bot_registration)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RegisterBotResponse | JSONResponse:
    try:
        bot = await registration.register(user_id=user.id, botfather_text=body.botfather_text)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        logger.exception("Unexpected error registering bot for user %s", user.id)
        cors_headers = build_cors_headers_for_origin(request.headers.get("origin"), settings)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"Error interno al registrar el bot: {e}"},
            headers=cors_headers,
        )
    return RegisterBotResponse(
        bot_id=bot.id,
        bot_username=bot.bot_username,
        chat_id=bot.chat_id,
        status="ok",
    )


@router.post("/send-test-news", status_code=status.HTTP_200_OK)
async def send_test_news(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    bot_repository: Annotated[UserBotRepository, Depends(get_user_bot_repository)],
    news_provider: Annotated[NewsProviderPort, Depends(get_event_news_provider)],
    use_case: Annotated[ProcessIncomingEvent, Depends(get_process_incoming_event_use_case)],
) -> SendTestNewsResponse:
    """Fetch a random demo news event, analyze it with Gemini, and send it as a
    Telegram notification to the authenticated user's registered bot."""
    bot = await bot_repository.get_by_user_id(user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tienes un bot de Telegram registrado. Registra uno primero.",
        )

    news_list = await news_provider.fetch_latest_news()
    if not news_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay eventos de noticias disponibles. Intenta de nuevo más tarde.",
        )

    news_event = random.choice(news_list)
    enriched = await use_case.execute(news_event)
    text = format_event_alert(enriched)
    client = TelegramBotClient(bot_token=bot.bot_token)
    await client.send_text(bot.chat_id, text, parse_mode="HTML")

    return SendTestNewsResponse(status="ok", event_title=enriched.original.title)


@router.post("/link-token", status_code=status.HTTP_201_CREATED)
async def create_link_token(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    token_repository: Annotated[
        TelegramLinkTokenRepository, Depends(get_telegram_link_token_repository)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelegramLinkTokenResponse:
    """Generate a short-lived, single-use linking token for the authenticated user, to be
    opened as `https://t.me/<bot_username>?start=<token>` (issue #14 acceptance criterion 1).

    `secrets.token_urlsafe` — unguessable, and the DB-backed `TelegramLinkTokenRepository`
    (not in-process) survives a restart or a different worker handling the eventual
    `/start <token>` webhook delivery.
    """
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.telegram_link_token_ttl_minutes)
    created = await token_repository.create(
        TelegramLinkToken(token=secrets.token_urlsafe(24), user_id=user.id, expires_at=expires_at)
    )
    deep_link_url = (
        f"https://t.me/{settings.telegram_bot_username}?start={created.token}"
        if settings.telegram_bot_username
        else None
    )
    return TelegramLinkTokenResponse(
        token=created.token, deep_link_url=deep_link_url, expires_at=created.expires_at
    )


@router.get("/link")
async def get_link_status(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    link_repository: Annotated[TelegramLinkRepository, Depends(get_telegram_link_repository)],
) -> TelegramLinkStatusResponse:
    """Whether the authenticated user currently has a linked Telegram chat."""
    link = await link_repository.get_by_user_id(user.id)
    return TelegramLinkStatusResponse(
        linked=link is not None, linked_at=link.linked_at if link else None
    )


@router.delete("/link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    link_repository: Annotated[TelegramLinkRepository, Depends(get_telegram_link_repository)],
) -> None:
    """Unlink the authenticated user's Telegram chat. Relinking is just running
    `/start <token>` again with a freshly generated token."""
    await link_repository.unlink(user.id)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    use_case: Annotated[LinkTelegramAccount | None, Depends(get_link_telegram_account_use_case)],
    briefing_handler: Annotated[
        BriefingCommandHandler | None, Depends(get_briefing_command_handler)
    ],
    signal_handler: Annotated[SignalCommandHandler | None, Depends(get_signal_command_handler)],
    simulate_handler: Annotated[
        SimulateCommandHandler | None, Depends(get_simulate_command_handler)
    ],
    impact_handler: Annotated[ImpactCommandHandler | None, Depends(get_impact_command_handler)],
    chat_handler: Annotated[ChatMessageHandler | None, Depends(get_chat_message_handler)],
    messenger: Annotated[TelegramMessenger | None, Depends(get_telegram_messenger)],
) -> dict[str, bool]:
    """Telegram webhook endpoint: Telegram POSTs every `Update` here once `setWebhook` is
    registered (see `infrastructure/telegram/register_telegram_webhook.py`, called from
    `main.py`'s lifespan).

    Recognizes five inbound shapes, via `parse_telegram_command`'s single dispatch point
    (issue #19, extending issue #14's `/start <token>`-only handling): `/start <token>`
    (linking), `/briefing`, `/signal <TICKER>`, `/simular <text>` (answered by the
    fleet), and `UnknownCommand` (an unrecognized or malformed command attempt, replied
    to with usage help rather than silently dropped). Every other update kind (edited
    messages, callback queries, ordinary chat text, ...) is acknowledged and ignored —
    `parse_telegram_command` returns `None` for those.

    `/simular` is special-cased: `simulate_handler.send_acknowledgement(...)` is awaited
    HERE (fast — one Telegram API call), but `simulate_handler.deliver_result(...)` (the
    full, slow Scenario Simulation graph run) is scheduled via `background_tasks` instead
    of awaited, so it runs AFTER this endpoint has already responded to Telegram — see
    `SimulateCommandHandler`'s docstring for why blocking the webhook response on that
    pipeline would be the wrong design.

    Always returns 200 (never raises for "nothing to do here" cases, NOR for an unexpected
    failure inside a handler call — see the `try`/`except` below) so Telegram doesn't
    retry-storm an update we deliberately don't act on, or one we simply failed to process;
    only a bad/missing webhook secret is rejected outright.
    """
    _verify_telegram_secret(request, settings)

    if use_case is None:
        logger.warning("Telegram webhook received but TELEGRAM_BOT_TOKEN is not configured")
        return {"ok": False}

    payload: dict[str, Any] = await request.json()
    command = parse_telegram_command(payload)
    if command is None:
        return {"ok": True}

    try:
        match command:
            case StartCommand():
                if command.token:
                    linked = await use_case.execute(token=command.token, chat_id=command.chat_id)
                    return {"ok": linked}
                if messenger is not None:
                    await messenger.send_text(command.chat_id, format_welcome_reply())
                return {"ok": True}
            case BriefingCommand():
                if briefing_handler is not None:
                    await briefing_handler.handle(command)
                return {"ok": True}
            case SignalCommand():
                if signal_handler is not None:
                    await signal_handler.handle(command)
                return {"ok": True}
            case SimulateCommand():
                if simulate_handler is not None:
                    should_run = await simulate_handler.send_acknowledgement(command)
                    if should_run:
                        background_tasks.add_task(simulate_handler.deliver_result, command)
                return {"ok": True}
            case ImpactCommand():
                if impact_handler is not None:
                    await impact_handler.handle(command)
                return {"ok": True}
            case ChatMessage():
                if chat_handler is not None:
                    await chat_handler.handle(command)
                return {"ok": True}
            case UnknownCommand():
                if messenger is not None:
                    await messenger.send_text(command.chat_id, format_unknown_command_reply())
                return {"ok": True}
            case _:
                return {"ok": True}
    except Exception:
        logger.exception(
            "Unhandled error handling Telegram command for chat_id=%s", command.chat_id
        )
        return {"ok": False}


@router.post("/webhook/{bot_id}", status_code=status.HTTP_200_OK)
async def telegram_webhook_for_bot(
    bot_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    bot_repository: Annotated[UserBotRepository, Depends(get_user_bot_repository)],
    container: Annotated[Container, Depends(get_container)],
    briefing_handler: Annotated[
        BriefingCommandHandler | None, Depends(get_briefing_command_handler)
    ],
    signal_handler: Annotated[SignalCommandHandler | None, Depends(get_signal_command_handler)],
    simulate_handler: Annotated[
        SimulateCommandHandler | None, Depends(get_simulate_command_handler)
    ],
    impact_handler: Annotated[ImpactCommandHandler | None, Depends(get_impact_command_handler)],
    chat_handler: Annotated[ChatMessageHandler | None, Depends(get_chat_message_handler)],
) -> dict[str, bool]:
    """Webhook endpoint for a user-registered Telegram bot.

    Identical logic to the main webhook, but uses the registered bot's token
    to send replies instead of the `.env` bot token. The user's bot is looked
    up by `bot_id` from the URL path.
    """
    bot = await bot_repository.get_by_id(bot_id)
    if bot is None:
        logger.warning("Unknown bot_id %s in webhook call", bot_id)
        return {"ok": False}

    payload: dict[str, Any] = await request.json()
    command = parse_telegram_command(payload)
    if command is None:
        return {"ok": True}

    messenger = TelegramBotClient(bot_token=bot.bot_token)

    try:
        match command:
            case StartCommand():
                await messenger.send_text(command.chat_id, format_welcome_reply())
                return {"ok": True}
            case BriefingCommand():
                if briefing_handler is not None:
                    await briefing_handler.handle(command)
                return {"ok": True}
            case SignalCommand():
                if signal_handler is not None:
                    await signal_handler.handle(command)
                return {"ok": True}
            case SimulateCommand():
                if simulate_handler is not None:
                    should_run = await simulate_handler.send_acknowledgement(command)
                    if should_run:
                        background_tasks.add_task(simulate_handler.deliver_result, command)
                return {"ok": True}
            case ImpactCommand():
                if impact_handler is not None:
                    await impact_handler.handle(command)
                return {"ok": True}
            case ChatMessage():
                handler = chat_handler or ChatMessageHandler(
                    agent_runner=container.get_agent_runner(),
                    messenger=messenger,
                )
                await handler.handle(command)
                return {"ok": True}
            case UnknownCommand():
                await messenger.send_text(command.chat_id, format_unknown_command_reply())
                return {"ok": True}
            case _:
                return {"ok": True}
    except Exception:
        logger.exception(
            "Unhandled error handling Telegram command for bot_id=%s, chat_id=%s",
            bot_id,
            command.chat_id,
        )
        return {"ok": False}


def _verify_telegram_secret(request: Request, settings: Settings) -> None:
    """Reject the webhook call if the `X-Telegram-Bot-Api-Secret-Token` header doesn't
    match the configured `TELEGRAM_WEBHOOK_SECRET` — see `setWebhook`'s `secret_token`
    param (https://core.telegram.org/bots/api#setwebhook).

    Fail-closed when the secret is unset: permissive only in a development/test env
    (with a one-time warning); in production/staging an unset secret rejects any
    anonymous POST with 403 instead of processing it."""
    if not settings.telegram_webhook_secret:
        if dev_fallback_allowed(settings):
            _warn_telegram_secret_unset_once()
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram webhook secret is not configured",
        )
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if header != settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret"
        )


def _warn_telegram_secret_unset_once() -> None:
    global _telegram_secret_warned
    if _telegram_secret_warned:
        return
    _telegram_secret_warned = True
    logger.warning(
        "TELEGRAM_WEBHOOK_SECRET is not set; the webhook accepts anonymous POSTs. "
        "This is only allowed in development/test environments."
    )
