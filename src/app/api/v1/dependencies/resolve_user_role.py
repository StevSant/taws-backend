from typing import Any

from app.api.v1.dependencies.dev_fallback_allowed import dev_fallback_allowed
from app.core.config import Settings
from app.domain.auth.entities import UserRole


def resolve_user_role(payload: dict[str, Any], settings: Settings) -> UserRole:
    """Resolve a caller's UserRole from a decoded JWT payload, failing safe to MEMBER.

    Precedence: (1) app_metadata.role claim, (2) top-level role claim, (3) DEV-ONLY demo
    email->role map (only consulted when dev_fallback_allowed(settings) is True), (4) MEMBER.
    In production the role comes ONLY from the verified JWT claims, never from the email.
    An invalid/unknown role literal is ignored (falls through), never trusted.
    """
    app_metadata = payload.get("app_metadata")
    claim = app_metadata.get("role") if isinstance(app_metadata, dict) else None
    if claim is None:
        claim = payload.get("role")

    role = _as_user_role(claim)
    if role is not None:
        return role

    email = payload.get("email")
    if email is not None and dev_fallback_allowed(settings):
        mapped = settings.demo_email_role_map.get(email)
        role = _as_user_role(mapped)
        if role is not None:
            return role

    return UserRole.MEMBER


def _as_user_role(value: Any) -> UserRole | None:
    if not isinstance(value, str):
        return None
    try:
        return UserRole(value)
    except ValueError:
        return None
