"""Tests for `require_current_user` — the strict auth dependency.

Core security regression guard (audit finding: fail-open auth): when Supabase Auth is
NOT configured (`SUPABASE_URL` unset), the dependency must ONLY fall back to the fake dev
user in a development/test env. In production it must fail CLOSED (401), never
authenticate everyone as `dev-user`.

Verification now uses asymmetric ES256 tokens verified against the project's JWKS
(derived from `SUPABASE_URL`), so the "auth configured" gate keys on `supabase_url`, not
the legacy `supabase_jwt_secret`. The verified-path tests stub `decode_bearer_token` so
they stay unit tests (no network / no real keypair) while still exercising the gate.

Behavior table (app_env x supabase_url x token -> outcome):

    url set   + valid token           -> user from token (verified via JWKS/ES256)
    url set   + missing/invalid/exp   -> 401
    url unset + development + token    -> identity from token (unverified, per-user)
    url unset + development + no token -> DEV_FALLBACK_USER
    url unset + production  + anything -> 401  (the regression guard)

Second regression guard (multi-user collapse): in the dev fallback, two callers presenting
two different tokens must resolve to two DIFFERENT identities — they must NOT both collapse
to the shared `DEV_FALLBACK_USER`, which would let real demo accounts share each other's
per-user data.
"""

import sys

import jwt
import pytest
from fastapi import HTTPException, status

from app.api.v1.dependencies.dev_fallback_user import DEV_FALLBACK_USER
from app.api.v1.dependencies.require_current_user import require_current_user
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings

# The package re-exports the `require_current_user` function under the same name as its
# submodule, so a plain `import ... as require_module` would bind the function, not the
# module. Fetch the actual module object to monkeypatch its `decode_bearer_token` symbol.
require_module = sys.modules["app.api.v1.dependencies.require_current_user"]

_URL = "https://example.supabase.co"


def _settings(*, app_env: str = "development", url: str | None = None) -> Settings:
    return Settings(app_env=app_env, supabase_url=url)


def _bearer(payload: dict, *, secret: str = "any-secret-signature-not-verified-here") -> str:
    # For the dev-fallback (unverified) path the signature is irrelevant.
    return "Bearer " + jwt.encode(payload, secret, algorithm="HS256")


def _stub_decode(monkeypatch: pytest.MonkeyPatch, result: CurrentUser | None) -> None:
    """Replace the verified ES256/JWKS decode so verified-path tests need no network."""
    monkeypatch.setattr(
        require_module, "decode_bearer_token", lambda _auth, _url, _settings: result
    )


# ---- Verified path: SUPABASE_URL set ---------------------------------------------------


def test_url_set_with_valid_token_returns_that_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_decode(monkeypatch, CurrentUser(id="real-user-id", email="real@user.io"))
    user = require_current_user(
        settings=_settings(app_env="production", url=_URL),
        authorization=_bearer({"sub": "real-user-id"}),
    )
    assert user.id == "real-user-id"
    assert user.email == "real@user.io"


def test_url_set_with_missing_token_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_decode(monkeypatch, None)  # never reached; guard fires on missing header
    with pytest.raises(HTTPException) as exc:
        require_current_user(settings=_settings(url=_URL), authorization=None)
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_url_set_with_invalid_token_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_decode(monkeypatch, None)  # decode fails (bad sig / expired / malformed) -> None
    with pytest.raises(HTTPException) as exc:
        require_current_user(settings=_settings(url=_URL), authorization=_bearer({"sub": "x"}))
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


# ---- Dev fallback path: SUPABASE_URL unset ---------------------------------------------


def test_url_unset_in_development_without_token_returns_dev_fallback_user() -> None:
    user = require_current_user(
        settings=_settings(app_env="development", url=None),
        authorization=None,
    )
    assert user == DEV_FALLBACK_USER


def test_url_unset_in_development_with_token_returns_identity_from_token() -> None:
    # In the dev fallback, an unverified token carries the caller's real identity so
    # distinct users stay distinct instead of collapsing to DEV_FALLBACK_USER.
    user = require_current_user(
        settings=_settings(app_env="development", url=None),
        authorization=_bearer({"sub": "alice", "email": "alice@user.io"}),
    )
    assert user.id == "alice"
    assert user.email == "alice@user.io"


def test_url_unset_in_development_keeps_distinct_users_distinct() -> None:
    # THE multi-user regression guard: two different tokens must NOT collapse to one id.
    settings = _settings(app_env="development", url=None)
    alice = require_current_user(settings=settings, authorization=_bearer({"sub": "alice"}))
    bob = require_current_user(settings=settings, authorization=_bearer({"sub": "bob"}))
    assert alice.id == "alice"
    assert bob.id == "bob"
    assert alice.id != bob.id


def test_url_unset_in_development_with_subless_token_returns_dev_fallback_user() -> None:
    # A token that carries no `sub` claim has no identity to preserve; anonymous local
    # poking still works via the shared dev user.
    user = require_current_user(
        settings=_settings(app_env="development", url=None),
        authorization=_bearer({"email": "nobody@user.io"}),
    )
    assert user == DEV_FALLBACK_USER


def test_url_unset_in_production_raises_401() -> None:
    # THE regression guard: no auth configured in prod must NOT authenticate everyone.
    with pytest.raises(HTTPException) as exc:
        require_current_user(
            settings=_settings(app_env="production", url=None),
            authorization=None,
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
