from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.api.v1.dependencies.decode_bearer_token import decode_bearer_token
from app.api.v1.dependencies.get_current_user import DEV_FALLBACK_USER
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings


def require_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve the current user, rejecting unauthenticated/invalid requests once Supabase
    Auth is configured.

    - No `SUPABASE_JWT_SECRET` configured at all: falls back to `DEV_FALLBACK_USER`, same
      as `get_current_user` — local dev without Supabase wired up stays usable.
    - `SUPABASE_JWT_SECRET` is configured but the request has no `Authorization` header,
      or the token is missing/invalid/expired: raises `HTTPException(401)` instead of
      silently succeeding as the fake dev user.

    Use this (not `get_current_user`) on routes that persist or expose per-user data —
    the watchlist CRUD and review endpoints.
    """
    if not settings.supabase_jwt_secret:
        return DEV_FALLBACK_USER

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
        )

    user = decode_bearer_token(authorization, settings.supabase_jwt_secret)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return user
