import jwt

from app.api.v1.dependencies.jwks_client import get_jwks_client
from app.api.v1.dependencies.resolve_user_role import resolve_user_role
from app.api.v1.dependencies.supabase_jwks_url import supabase_jwks_url
from app.api.v1.schemas import CurrentUser
from app.core.config import Settings


def verify_realtime_ws_token(token: str, settings: Settings) -> CurrentUser | None:
    """Verify a Supabase ES256 access token passed as a WebSocket `?token=` query param.

    A browser `WebSocket` cannot set an `Authorization` header, so the Realtime WS
    endpoint carries the JWT in the query string and verifies it here — the plain,
    `Depends`-free twin of `decode_bearer_token`. The same ES256/JWKS guarantees hold:

    - Algorithm is PINNED to `["ES256"]`; a forged HS256/`alg:none` token is rejected.
    - Verified against the project's JWKS public key (`{SUPABASE_URL}/auth/v1/.well-known/
      jwks.json`), fetched via the shared cached `PyJWKClient`.

    Fails CLOSED — returns `None` on ANY failure (empty/malformed token, bad signature,
    expired, missing `sub`, JWKS fetch error) so the endpoint can `close(1008)`. Unlike
    the HTTP `require_current_user`, there is NO dev fallback: without `SUPABASE_URL`
    configured this returns `None`, because an unverified voice session would bill OpenAI
    under an unauthenticated caller. `PyJWKClientError` subclasses `jwt.PyJWTError`, so a
    JWKS connection failure is covered by the single except.
    """
    if not token or not settings.supabase_url:
        return None

    jwks_url = supabase_jwks_url(settings.supabase_url)
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
    role = resolve_user_role(payload, settings)
    return CurrentUser(id=str(subject), email=payload.get("email"), role=role)
