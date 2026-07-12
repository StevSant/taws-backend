"""Role-extraction tests for `decode_unverified_identity` (dev fallback path).

This decoder is dev-only. After reading the (unverified) identity it resolves the
caller's `UserRole` via `resolve_user_role(payload, settings)`. Tests use a dev `app_env`
so the demo-email fallback is exercised, and also confirm an explicit claim wins.
"""

import jwt

from app.api.v1.dependencies.decode_unverified_identity import decode_unverified_identity
from app.core.config import Settings
from app.domain.auth.entities import UserRole

_ANY_SECRET = "irrelevant-because-signature-is-not-verified"


def _bearer(payload: dict) -> str:
    return "Bearer " + jwt.encode(payload, _ANY_SECRET, algorithm="HS256")


def _settings(*, app_env: str = "development") -> Settings:
    return Settings(app_env=app_env)


def test_role_claim_is_attached() -> None:
    user = decode_unverified_identity(
        _bearer({"sub": "alice", "app_metadata": {"role": "compliance"}}),
        _settings(),
    )
    assert user is not None
    assert user.role is UserRole.COMPLIANCE


def test_demo_email_grants_role_in_dev() -> None:
    user = decode_unverified_identity(
        _bearer({"sub": "carol", "email": "compliance@midas.demo"}),
        _settings(app_env="development"),
    )
    assert user is not None
    assert user.role is UserRole.COMPLIANCE


def test_unknown_caller_defaults_to_member() -> None:
    user = decode_unverified_identity(
        _bearer({"sub": "bob", "email": "bob@nowhere.io"}),
        _settings(app_env="development"),
    )
    assert user is not None
    assert user.role is UserRole.MEMBER
