from app.core.config import Settings

# Environment names where authentication may degrade to the fake `DEV_FALLBACK_USER`
# when no `SUPABASE_JWT_SECRET` is configured. Anything NOT in this set (production,
# staging, or any unrecognized value) is treated as non-dev and fails closed. Defined
# once here so the dev-vs-prod decision isn't re-derived from scattered string literals
# (reused by the Telegram webhook guard and the startup guard).
DEV_ENV_NAMES: frozenset[str] = frozenset({"development", "dev", "test", "local"})


def dev_fallback_allowed(settings: Settings) -> bool:
    """Whether the fake dev user may stand in for a real authenticated user.

    True only in a development/test/local env — used to keep local dev usable before
    Supabase Auth is wired up. False everywhere else so a missing secret fails closed
    instead of authenticating every request as `dev-user`.

    `app_env` is normalized (trimmed + lowercased) before matching so a miscased or
    padded value (e.g. "Production", " development ") is classified deterministically
    rather than silently falling into the wrong branch.
    """
    return settings.app_env.strip().lower() in DEV_ENV_NAMES
