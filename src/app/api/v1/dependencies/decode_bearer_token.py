import jwt

from app.api.v1.schemas import CurrentUser


def decode_bearer_token(authorization: str, jwt_secret: str) -> CurrentUser | None:
    """Verify a Supabase HS256 JWT from an `Authorization: Bearer <token>` header value.

    Returns `None` if the token is malformed, expired, fails signature verification, or
    lacks a `sub` claim, instead of raising — shared by `get_current_user` (lenient) and
    `require_current_user` (strict), which each decide what to do with a `None` result.
    """
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], options={"verify_aud": False})
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if not subject:
        return None
    return CurrentUser(id=str(subject), email=payload.get("email"))
