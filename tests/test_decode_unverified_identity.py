"""Unit tests for `decode_unverified_identity` — the dev-fallback-only identity reader.

This decoder reads the `sub`/`email` claims from a `Bearer <jwt>` WITHOUT verifying the
signature. It exists SOLELY so that, in a local dev env with no `SUPABASE_JWT_SECRET`
configured, distinct callers keep distinct identities instead of collapsing to one shared
`DEV_FALLBACK_USER`. It must never be used when a secret is configured (that path uses the
verified `decode_bearer_token`).

Contract:
    any token with a `sub` claim   -> CurrentUser(id=str(sub), email=email-or-None)
    token without a `sub` claim    -> None
    malformed / non-JWT garbage    -> None
"""

import jwt

from app.api.v1.dependencies.decode_unverified_identity import decode_unverified_identity
from app.core.config import Settings

_ANY_SECRET = "irrelevant-because-signature-is-not-verified"
# Dev env — this decoder only runs in the dev fallback anyway; role resolution is
# covered separately in `test_decode_unverified_identity_role.py`.
_SETTINGS = Settings(app_env="development")


def _bearer(payload: dict, *, secret: str = _ANY_SECRET) -> str:
    return "Bearer " + jwt.encode(payload, secret, algorithm="HS256")


def test_token_with_sub_returns_current_user() -> None:
    user = decode_unverified_identity(
        _bearer({"sub": "alice", "email": "alice@user.io"}), _SETTINGS
    )
    assert user is not None
    assert user.id == "alice"
    assert user.email == "alice@user.io"


def test_token_with_sub_but_no_email_returns_user_with_none_email() -> None:
    user = decode_unverified_identity(_bearer({"sub": "bob"}), _SETTINGS)
    assert user is not None
    assert user.id == "bob"
    assert user.email is None


def test_non_string_sub_is_coerced_to_string() -> None:
    user = decode_unverified_identity(_bearer({"sub": 12345}), _SETTINGS)
    assert user is not None
    assert user.id == "12345"


def test_token_signed_with_any_secret_is_accepted() -> None:
    # Signature is intentionally NOT verified — a token signed with an unrelated secret
    # still yields its identity in the dev fallback.
    token = _bearer({"sub": "carol"}, secret="a-completely-unrelated-secret-32-bytes!")
    user = decode_unverified_identity(token, _SETTINGS)
    assert user is not None
    assert user.id == "carol"


def test_token_without_sub_returns_none() -> None:
    assert decode_unverified_identity(_bearer({"email": "nobody@user.io"}), _SETTINGS) is None


def test_garbage_token_returns_none() -> None:
    assert decode_unverified_identity("Bearer not-a-real-jwt", _SETTINGS) is None


def test_empty_token_returns_none() -> None:
    assert decode_unverified_identity("Bearer ", _SETTINGS) is None
