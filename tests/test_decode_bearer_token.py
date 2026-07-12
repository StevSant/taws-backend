"""Unit tests for `decode_bearer_token` — ES256/JWKS verification (fail-closed).

Supabase migrated to asymmetric JWT signing keys (ECC P-256 => ES256). Tokens are now
verified against the project's JWKS public key, with the algorithm PINNED to ES256 so an
attacker cannot downgrade to HS256 (algorithm-confusion) or "none". Any failure —
malformed token, bad signature, expired, missing `sub`, or a JWKS fetch/connection error
— returns `None` (the caller turns that into a 401), never an exception / 500.

Tests generate a throwaway EC P-256 keypair, build a `PyJWK` from the public key, and
stub `get_jwks_client` so no network call happens.
"""

import sys
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt import PyJWK

from app.api.v1.dependencies.decode_bearer_token import decode_bearer_token
from app.api.v1.dependencies.jwks_client import get_jwks_client
from app.core.config import Settings

# The package re-exports `decode_bearer_token` (the function) under the same name as its
# submodule, so `import ... as decode_module` would bind the function. Fetch the real
# module object so we can monkeypatch its `get_jwks_client` reference (no network).
decode_module = sys.modules["app.api.v1.dependencies.decode_bearer_token"]

_KID = "test-kid-1"
_JWKS_URL = "https://example.supabase.co/auth/v1/.well-known/jwks.json"
# Role resolution reads from the verified claims; a production env keeps the dev-only
# email fallback out of the picture for these signature/verification tests.
_SETTINGS = Settings(app_env="production")


@pytest.fixture
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _jwk_from_public(private_key: ec.EllipticCurvePrivateKey, *, kid: str = _KID) -> PyJWK:
    algo = jwt.get_algorithm_by_name("ES256")
    jwk_dict = algo.to_jwk(private_key.public_key(), as_dict=True)
    jwk_dict.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return PyJWK.from_dict(jwk_dict)


class _StubJwksClient:
    """Stands in for `PyJWKClient`, returning a preset signing key without network."""

    def __init__(self, signing_key: PyJWK) -> None:
        self._signing_key = signing_key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        return self._signing_key


class _RaisingJwksClient:
    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        raise jwt.PyJWKClientError("boom: JWKS unreachable")


def _install_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    get_jwks_client.cache_clear()
    monkeypatch.setattr(decode_module, "get_jwks_client", lambda _url: client)


def _sign(private_key: ec.EllipticCurvePrivateKey, payload: dict, *, kid: str = _KID) -> str:
    return "Bearer " + jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": kid})


def _valid_payload() -> dict:
    return {
        "sub": "real-user-id",
        "email": "real@user.io",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }


def test_valid_es256_token_returns_current_user(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    user = decode_bearer_token(_sign(ec_key, _valid_payload()), _JWKS_URL, _SETTINGS)
    assert user is not None
    assert user.id == "real-user-id"
    assert user.email == "real@user.io"


def test_expired_token_returns_none(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    expired = _sign(ec_key, {"sub": "x", "exp": datetime.now(UTC) - timedelta(hours=1)})
    assert decode_bearer_token(expired, _JWKS_URL, _SETTINGS) is None


def test_wrong_key_signature_returns_none(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    # Token signed by an attacker key; JWKS returns the (different) legitimate public key.
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    forged = _sign(attacker_key, _valid_payload())
    assert decode_bearer_token(forged, _JWKS_URL, _SETTINGS) is None


def test_hs256_alg_confusion_token_returns_none(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    # Algorithm-confusion attempt: token forged with HS256 must be rejected because the
    # accepted algorithms list is pinned to ES256 only.
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    hs_token = "Bearer " + jwt.encode(
        _valid_payload(), "attacker-shared-secret", algorithm="HS256", headers={"kid": _KID}
    )
    assert decode_bearer_token(hs_token, _JWKS_URL, _SETTINGS) is None


def test_malformed_token_returns_none(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    assert decode_bearer_token("Bearer not-a-real-jwt", _JWKS_URL, _SETTINGS) is None


def test_missing_sub_returns_none(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    payload = {"email": "nobody@user.io", "exp": datetime.now(UTC) + timedelta(hours=1)}
    no_sub = _sign(ec_key, payload)
    assert decode_bearer_token(no_sub, _JWKS_URL, _SETTINGS) is None


def test_jwks_client_error_returns_none_fail_closed(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    # A JWKS fetch / connection failure must fail closed (None), not raise (500).
    _install_client(monkeypatch, _RaisingJwksClient())
    assert decode_bearer_token(_sign(ec_key, _valid_payload()), _JWKS_URL, _SETTINGS) is None
