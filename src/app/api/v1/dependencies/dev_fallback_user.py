from app.api.v1.schemas import CurrentUser

# The fake user substituted for a real authenticated one in local dev, when no
# `SUPABASE_JWT_SECRET` is configured. Only ever returned when `dev_fallback_allowed`
# permits it (dev/test envs) — never in production. See `require_current_user`.
DEV_FALLBACK_USER = CurrentUser(id="dev-user", email="dev@example.com")
