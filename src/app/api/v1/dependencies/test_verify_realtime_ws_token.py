"""Tests for `verify_realtime_ws_token` — the JWT-from-query-param auth helper.

A browser WebSocket cannot set an `Authorization` header, so the Realtime WS endpoint
carries the Supabase access token as a `?token=` query param and verifies it with this
plain callable (no FastAPI `Depends`). This mirrors the ES256/JWKS verification done by
`decode_bearer_token`, so the same forged-token / expired-token guarantees apply. The
JWKS lookup is monkeypatched to a locally generated EC P-256 key so no network is hit.
"""

import sys
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.v1.dependencies.verify_realtime_ws_token import verify_realtime_ws_token
from app.core.config import Settings

# Grab the real MODULE object from sys.modules so monkeypatch can swap `get_jwks_client`
# on the module namespace. `import ... as _module` would instead bind the re-exported
# FUNCTION of the same name (the package `__init__` overwrites the submodule attribute
# on the package), which has no `get_jwks_client` attribute.
_module = sys.modules["app.api.v1.dependencies.verify_realtime_ws_token"]


def _make_es256_keypair() -> tuple[ec.EllipticCurvePrivateKey, Any]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def _encode(private_key: ec.EllipticCurvePrivateKey, claims: dict[str, Any]) -> str:
    return jwt.encode(claims, private_key, algorithm="ES256")


class _FakeSigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey(self._public_key)


def _patch_jwks(monkeypatch: Any, public_key: Any) -> None:
    monkeypatch.setattr(_module, "get_jwks_client", lambda _url: _FakeJWKSClient(public_key))


def _settings() -> Settings:
    return Settings(supabase_url="https://proj.supabase.co")


def test_valid_token_returns_user(monkeypatch: Any) -> None:
    private_key, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)
    token = _encode(
        private_key,
        {"sub": "user-123", "email": "v@example.com", "exp": int(time.time()) + 600},
    )

    user = verify_realtime_ws_token(token, _settings())

    assert user is not None
    assert user.id == "user-123"
    assert user.email == "v@example.com"


def test_expired_token_returns_none(monkeypatch: Any) -> None:
    private_key, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)
    token = _encode(private_key, {"sub": "user-123", "exp": int(time.time()) - 10})

    assert verify_realtime_ws_token(token, _settings()) is None


def test_token_signed_by_wrong_key_returns_none(monkeypatch: Any) -> None:
    signing_key, _ = _make_es256_keypair()
    _, other_public_key = _make_es256_keypair()
    # JWKS serves an unrelated public key -> signature verification fails.
    _patch_jwks(monkeypatch, other_public_key)
    token = _encode(signing_key, {"sub": "user-123", "exp": int(time.time()) + 600})

    assert verify_realtime_ws_token(token, _settings()) is None


def test_missing_sub_returns_none(monkeypatch: Any) -> None:
    private_key, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)
    token = _encode(private_key, {"email": "v@example.com", "exp": int(time.time()) + 600})

    assert verify_realtime_ws_token(token, _settings()) is None


def test_garbage_token_returns_none(monkeypatch: Any) -> None:
    _, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)

    assert verify_realtime_ws_token("not-a-jwt", _settings()) is None


def test_hs256_alg_confusion_token_returns_none(monkeypatch: Any) -> None:
    # Algorithm-confusion attempt: a token forged with HS256 must be rejected because the
    # accepted algorithms list is pinned to ES256 only (mirrors decode_bearer_token's
    # test_hs256_alg_confusion_token_returns_none).
    _, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)
    hs_token = jwt.encode(
        {"sub": "user-123", "exp": int(time.time()) + 600},
        "attacker-shared-secret",
        algorithm="HS256",
    )

    assert verify_realtime_ws_token(hs_token, _settings()) is None


def test_empty_token_returns_none() -> None:
    assert verify_realtime_ws_token("", _settings()) is None


def test_none_supabase_url_returns_none(monkeypatch: Any) -> None:
    """No Supabase URL configured -> no JWKS to verify against -> unauthenticated.

    The WS endpoint must fail closed here rather than reusing the HTTP dev-fallback path,
    since an unverified voice session would bill OpenAI under an unauthenticated caller.
    """
    private_key, public_key = _make_es256_keypair()
    _patch_jwks(monkeypatch, public_key)
    token = _encode(private_key, {"sub": "user-123", "exp": int(time.time()) + 600})

    assert verify_realtime_ws_token(token, Settings(supabase_url=None)) is None
