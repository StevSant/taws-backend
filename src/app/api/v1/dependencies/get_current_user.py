from typing import Annotated

from fastapi import Depends, Header

from app.api.v1.dependencies.decode_bearer_token import decode_bearer_token
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings

DEV_FALLBACK_USER = CurrentUser(id="dev-user", email="dev@example.com")


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve the current user, falling back to a fake dev user instead of rejecting.

    Dev-friendly by design: if no JWT secret is configured, no token was sent, or the
    token fails verification, this falls back to `DEV_FALLBACK_USER` instead of
    raising — so routes using this dependency (e.g. chat) stay usable before Supabase
    Auth is wired up end-to-end.

    This is intentionally lenient even when a JWT secret *is* configured, so it never
    regresses existing routes. Routes that must reject unauthenticated/invalid requests
    (the watchlist + review endpoints) should depend on `require_current_user` instead.
    """
    if not settings.supabase_jwt_secret or not authorization:
        return DEV_FALLBACK_USER

    user = decode_bearer_token(authorization, settings.supabase_jwt_secret)
    return user if user is not None else DEV_FALLBACK_USER
