"""Tests for `require_current_user` — the strict auth dependency.

Core security regression guard (audit finding: fail-open auth): when
`SUPABASE_JWT_SECRET` is unset, the dependency must ONLY fall back to the fake dev user
in a development/test env. In production it must fail CLOSED (401), never authenticate
everyone as `dev-user`.

Behavior table (app_env x secret -> outcome):

    secret set   + valid token          -> user from token
    secret set   + missing/invalid/exp  -> 401
    secret unset + app_env=development   -> DEV_FALLBACK_USER
    secret unset + app_env=production    -> 401  (the regression guard)
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException, status

from app.api.v1.dependencies.dev_fallback_user import DEV_FALLBACK_USER
from app.api.v1.dependencies.require_current_user import require_current_user
from app.core.config import Settings

_SECRET = "test-jwt-secret-at-least-32-bytes-long!"


def _settings(*, app_env: str = "development", secret: str | None = None) -> Settings:
    return Settings(app_env=app_env, supabase_jwt_secret=secret)


def _bearer(payload: dict, *, secret: str = _SECRET) -> str:
    return "Bearer " + jwt.encode(payload, secret, algorithm="HS256")


def _valid_token() -> str:
    exp = datetime.now(UTC) + timedelta(hours=1)
    return _bearer({"sub": "real-user-id", "email": "real@user.io", "exp": exp})


def test_secret_set_with_valid_token_returns_that_user() -> None:
    user = require_current_user(
        settings=_settings(app_env="production", secret=_SECRET),
        authorization=_valid_token(),
    )
    assert user.id == "real-user-id"
    assert user.email == "real@user.io"


def test_secret_set_with_missing_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        require_current_user(settings=_settings(secret=_SECRET), authorization=None)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_secret_set_with_invalid_signature_raises_401() -> None:
    bad = _bearer({"sub": "x"}, secret="a-totally-different-secret-32-bytes-long!")
    with pytest.raises(HTTPException) as exc:
        require_current_user(settings=_settings(secret=_SECRET), authorization=bad)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_secret_set_with_expired_token_raises_401() -> None:
    expired = _bearer({"sub": "x", "exp": datetime.now(UTC) - timedelta(hours=1)})
    with pytest.raises(HTTPException) as exc:
        require_current_user(settings=_settings(secret=_SECRET), authorization=expired)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_secret_unset_in_development_returns_dev_fallback_user() -> None:
    user = require_current_user(
        settings=_settings(app_env="development", secret=None),
        authorization=None,
    )
    assert user == DEV_FALLBACK_USER


def test_secret_unset_in_production_raises_401() -> None:
    # THE regression guard: empty secret in prod must NOT authenticate everyone.
    with pytest.raises(HTTPException) as exc:
        require_current_user(
            settings=_settings(app_env="production", secret=None),
            authorization=None,
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
