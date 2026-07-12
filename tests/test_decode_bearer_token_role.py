"""Role-extraction tests for `decode_bearer_token`.

After the identity is built from a verified ES256/JWKS token, `decode_bearer_token`
resolves the caller's `UserRole` via `resolve_user_role(payload, settings)` and attaches
it to the returned `CurrentUser`. The verified-claim path is environment-independent; the
demo-email fallback is dev-only (exercised here with an explicit dev `app_env`).
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
from app.domain.auth.entities import UserRole

decode_module = sys.modules["app.api.v1.dependencies.decode_bearer_token"]

_KID = "test-kid-1"
_JWKS_URL = "https://example.supabase.co/auth/v1/.well-known/jwks.json"


@pytest.fixture
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _jwk_from_public(private_key: ec.EllipticCurvePrivateKey, *, kid: str = _KID) -> PyJWK:
    algo = jwt.get_algorithm_by_name("ES256")
    jwk_dict = algo.to_jwk(private_key.public_key(), as_dict=True)
    jwk_dict.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return PyJWK.from_dict(jwk_dict)


class _StubJwksClient:
    def __init__(self, signing_key: PyJWK) -> None:
        self._signing_key = signing_key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        return self._signing_key


def _install_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    get_jwks_client.cache_clear()
    monkeypatch.setattr(decode_module, "get_jwks_client", lambda _url: client)


def _sign(private_key: ec.EllipticCurvePrivateKey, payload: dict, *, kid: str = _KID) -> str:
    return "Bearer " + jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": kid})


def _base_payload(**extra: object) -> dict:
    return {
        "sub": "real-user-id",
        "email": "real@user.io",
        "exp": datetime.now(UTC) + timedelta(hours=1),
        **extra,
    }


def _settings(*, app_env: str = "production") -> Settings:
    return Settings(app_env=app_env)


def test_app_metadata_role_claim_is_attached(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    token = _sign(ec_key, _base_payload(app_metadata={"role": "compliance"}))
    user = decode_bearer_token(token, _JWKS_URL, _settings())
    assert user is not None
    assert user.role is UserRole.COMPLIANCE


def test_missing_role_claim_defaults_to_member_in_production(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    # Even with the demo email, prod must not grant a role from the email.
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    token = _sign(ec_key, _base_payload(email="compliance@midas.demo"))
    user = decode_bearer_token(token, _JWKS_URL, _settings(app_env="production"))
    assert user is not None
    assert user.role is UserRole.MEMBER


def test_demo_email_grants_role_in_dev(
    monkeypatch: pytest.MonkeyPatch, ec_key: ec.EllipticCurvePrivateKey
) -> None:
    _install_client(monkeypatch, _StubJwksClient(_jwk_from_public(ec_key)))
    token = _sign(ec_key, _base_payload(email="gestor@midas.demo"))
    user = decode_bearer_token(token, _JWKS_URL, _settings(app_env="development"))
    assert user is not None
    assert user.role is UserRole.PORTFOLIO
