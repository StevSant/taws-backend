import jwt

from app.api.v1.dependencies.jwks_client import get_jwks_client
from app.api.v1.schemas import CurrentUser


def decode_bearer_token(authorization: str, jwks_url: str) -> CurrentUser | None:
    """Verify a Supabase ES256 JWT from an `Authorization: Bearer <token>` header value.

    Supabase migrated to asymmetric JWT signing keys (ECC P-256 => ES256): access tokens
    are verified against the project's JWKS public key, fetched from `jwks_url`.

    The accepted algorithms list is PINNED to `["ES256"]` — the alg is never read from the
    token header to decide verification — so a forged HS256 token (algorithm-confusion) or
    an `alg: none` token is rejected outright.

    Fails CLOSED: returns `None` on ANY failure (malformed token, bad signature, expired,
    missing `sub`, or a JWKS fetch/connection error), instead of raising — used by
    `require_current_user`, which turns a `None` result into a 401. `PyJWKClientError`
    (raised on a JWKS fetch/connection failure) subclasses `jwt.PyJWTError`, so it is
    covered by the single except.
    """
    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if not subject:
        return None
    return CurrentUser(id=str(subject), email=payload.get("email"))
