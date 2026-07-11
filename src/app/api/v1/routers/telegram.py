import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.v1.dependencies import (
    get_briefing_command_handler,
    get_chat_message_handler,
    get_impact_command_handler,
    get_link_telegram_account_use_case,
    get_signal_command_handler,
    get_simulate_command_handler,
    get_telegram_link_repository,
    get_telegram_link_token_repository,
    get_telegram_messenger,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser, TelegramLinkStatusResponse, TelegramLinkTokenResponse
from app.application.telegram.use_cases import LinkTelegramAccount
from app.core.config import Settings, get_settings
from app.domain.telegram.entities import TelegramLinkToken
from app.domain.telegram.ports import (
    TelegramLinkRepository,
    TelegramLinkTokenRepository,
    TelegramMessenger,
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
    UnknownCommand,
    format_unknown_command_reply,
    format_welcome_reply,
    parse_telegram_command,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


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
    impact_handler: Annotated[
        ImpactCommandHandler | None, Depends(get_impact_command_handler)
    ],
    chat_handler: Annotated[
        ChatMessageHandler | None, Depends(get_chat_message_handler)
    ],
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

    # "Always ack 200 to Telegram" is a webhook-contract concern (avoid retry storms), not
    # a domain concern — so it's enforced HERE at the router boundary, not inside any
    # handler (same split as `chat.py`'s SSE stream: the domain layer surfaces its own
    # errors, the transport boundary decides how to keep its contract intact around
    # them). `LinkTelegramAccount.execute()`'s `consume()`/`link()` can raise on a
    # transient Supabase/network error; that's safe to swallow because `consume()` is
    # idempotent — a Telegram retry of the same `/start <token>` update after a transient
    # failure just re-attempts the same (safe) consume, it doesn't double-link anything.
    # The other handlers' lookups are all safe to retry too (reads, or — for `/simular`'s
    # ack step — a message send that's fine to duplicate on a genuine Telegram retry).
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
            case _:  # pragma: no cover — TelegramCommand is a closed union; unreachable.
                return {"ok": True}
    except Exception:  # noqa: BLE001 — must always ack 200; see docstring above.
        logger.exception(
            "Unhandled error handling Telegram command for chat_id=%s", command.chat_id
        )
        return {"ok": False}


def _verify_telegram_secret(request: Request, settings: Settings) -> None:
    """Reject the webhook call if `TELEGRAM_WEBHOOK_SECRET` is configured and the request's
    `X-Telegram-Bot-Api-Secret-Token` header doesn't match — see `setWebhook`'s
    `secret_token` param (https://core.telegram.org/bots/api#setwebhook). Skipped entirely
    when no secret is configured (fine for local/dev)."""
    if not settings.telegram_webhook_secret:
        return
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if header != settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret"
        )
