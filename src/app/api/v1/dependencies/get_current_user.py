from typing import Annotated

import jwt
from fastapi import Depends, Header

from app.api.v1.schemas import CurrentUser
from app.core.config import Settings, get_settings

_DEV_FALLBACK_USER = CurrentUser(id="dev-user", email="dev@example.com")


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Verify the Supabase JWT (HS256) from the `Authorization: Bearer <token>` header.

    Dev-friendly by design: if no JWT secret is configured, no token was sent, or the
    token fails verification, this falls back to a fake user instead of raising —
    so the API is fully usable before Supabase Auth is wired up end-to-end.
    """
    if not settings.supabase_jwt_secret or not authorization:
        return _DEV_FALLBACK_USER

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return _DEV_FALLBACK_USER

    return CurrentUser(
        id=str(payload.get("sub", _DEV_FALLBACK_USER.id)), email=payload.get("email")
    )
