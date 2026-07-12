import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.api.v1.dependencies.decode_bearer_token import decode_bearer_token
from app.api.v1.dependencies.decode_unverified_identity import decode_unverified_identity
from app.api.v1.dependencies.dev_fallback_allowed import dev_fallback_allowed
from app.api.v1.dependencies.dev_fallback_user import DEV_FALLBACK_USER
from app.api.v1.dependencies.supabase_jwks_url import supabase_jwks_url
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Emit the "no secret, falling back to dev user" warning only once per process instead
# of on every unauthenticated request, so a dev run isn't flooded with the same line.
_dev_fallback_warned = False


def require_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Resolve the current user, failing CLOSED when Supabase Auth can't be verified.

    - `SUPABASE_URL` configured (JWKS reachable): verify the ES256 JWT against the
      project's JWKS public key — raises `HTTPException(401)` on a missing/invalid/expired
      token instead of silently succeeding.
    - `SUPABASE_URL` NOT configured:
        - in a development/test env (`dev_fallback_allowed`): keep local dev usable
          without Supabase wired up, and log a one-time warning. If the caller presents a
          bearer token, read its identity WITHOUT verifying the signature so distinct
          callers stay distinct (real demo accounts must not share per-user data); if no
          token (or no `sub`) is present, fall back to the shared `DEV_FALLBACK_USER` so
          anonymous local poking still works.
        - otherwise (production/staging/unrecognized env): raise `HTTPException(401)` —
          it must never authenticate every request as the fake dev user.
    """
    if not settings.supabase_url:
        if dev_fallback_allowed(settings):
            _warn_dev_fallback_once()
            if authorization:
                unverified_user = decode_unverified_identity(authorization, settings)
                if unverified_user is not None:
                    return unverified_user
            return DEV_FALLBACK_USER
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured",
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
        )

    user = decode_bearer_token(authorization, supabase_jwks_url(settings.supabase_url), settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    return user


def _warn_dev_fallback_once() -> None:
    global _dev_fallback_warned
    if _dev_fallback_warned:
        return
    _dev_fallback_warned = True
    logger.warning(
        "SUPABASE_JWT_SECRET is not set; authenticating requests as the dev fallback "
        "user. This is only allowed in development/test environments."
    )
