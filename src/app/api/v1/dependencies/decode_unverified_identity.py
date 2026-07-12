import jwt

from app.api.v1.schemas import CurrentUser


def decode_unverified_identity(authorization: str) -> CurrentUser | None:
    """Read the identity from an `Authorization: Bearer <token>` WITHOUT verifying it.

    DANGER — dev fallback ONLY. This decodes the JWT with signature verification DISABLED,
    so it trusts whatever `sub`/`email` the caller presents. It exists solely to keep
    distinct callers distinct in a local dev env where no `SUPABASE_JWT_SECRET` is
    configured (otherwise every caller collapses to the shared `DEV_FALLBACK_USER` and
    real demo accounts share each other's per-user data). It MUST NEVER be used when a
    secret is configured — that path uses the verified `decode_bearer_token` instead.

    Returns `CurrentUser(id=str(sub), email=payload.get("email"))` when a `sub` claim is
    present, else `None` (malformed token, non-JWT garbage, or missing `sub`) — used by
    `require_current_user`, which decides what to do with a `None` result.
    """
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token, options={"verify_signature": False, "verify_aud": False}
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if not subject:
        return None
    return CurrentUser(id=str(subject), email=payload.get("email"))
