import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.v1.dependencies import (
    get_link_telegram_account_use_case,
    get_telegram_link_repository,
    get_telegram_link_token_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser, TelegramLinkStatusResponse, TelegramLinkTokenResponse
from app.application.telegram.use_cases import LinkTelegramAccount
from app.core.config import Settings, get_settings
from app.domain.telegram.entities import TelegramLinkToken
from app.domain.telegram.ports import TelegramLinkRepository, TelegramLinkTokenRepository
from app.infrastructure.telegram import parse_start_command

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
    settings: Annotated[Settings, Depends(get_settings)],
    use_case: Annotated[LinkTelegramAccount | None, Depends(get_link_telegram_account_use_case)],
) -> dict[str, bool]:
    """Telegram webhook endpoint: Telegram POSTs every `Update` here once `setWebhook` is
    registered (see `infrastructure/telegram/register_telegram_webhook.py`, called from
    `main.py`'s lifespan). Only reacts to a `/start <token>` text message — every other
    update kind is acknowledged and ignored.

    Always returns 200 (never raises for "nothing to do here" cases, NOR for an unexpected
    failure inside `use_case.execute` — see the `try`/`except` below) so Telegram doesn't
    retry-storm an update we deliberately don't act on, or one we simply failed to process;
    only a bad/missing webhook secret is rejected outright.
    """
    _verify_telegram_secret(request, settings)

    if use_case is None:
        logger.warning("Telegram webhook received but TELEGRAM_BOT_TOKEN is not configured")
        return {"ok": False}

    payload: dict[str, Any] = await request.json()
    command = parse_start_command(payload)
    if command is None:
        return {"ok": True}

    # "Always ack 200 to Telegram" is a webhook-contract concern (avoid retry storms), not
    # a domain concern — so it's enforced HERE at the router boundary, not inside
    # `LinkTelegramAccount.execute()` (same split as `chat.py`'s SSE stream: the domain
    # layer surfaces its own errors, the transport boundary decides how to keep its
    # contract intact around them). `consume()`/`link()` can raise on a transient
    # Supabase/network error; that's safe to swallow because `consume()` is idempotent —
    # a Telegram retry of the same `/start <token>` update after a transient failure just
    # re-attempts the same (safe) consume, it doesn't double-link anything.
    try:
        linked = await use_case.execute(token=command.token, chat_id=command.chat_id)
    except Exception:  # noqa: BLE001 — must always ack 200; see docstring above.
        logger.exception("Unhandled error linking Telegram chat_id=%s via webhook", command.chat_id)
        return {"ok": False}
    return {"ok": linked}


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
