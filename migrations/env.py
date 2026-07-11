"""Alembic environment script.

No SQLAlchemy ORM models / `target_metadata` here on purpose: the app's runtime data
layer is `supabase-py` (PostgREST), not SQLAlchemy — see
`src/app/infrastructure/persistence/`. Alembic is used purely as a raw-SQL migration
*runner* (versioning, `upgrade`/`downgrade`, the `alembic_version` tracking table),
not an ORM — so there's no autogenerate support, and every revision's `upgrade()`/
`downgrade()` is hand-written SQL via `op.execute(...)`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> str:
    """Resolve the migration target from `Settings.database_url` (`.env`).

    Never from `alembic.ini` — keeps the Supabase Postgres connection string (with
    credentials) out of a file that would otherwise get committed. Supabase hands out
    a plain `postgresql://` connection string; SQLAlchemy needs the driver named
    explicitly to pick `psycopg` (v3, the driver installed for Alembic here), so
    `postgresql://` is rewritten to `postgresql+psycopg://` when not already scoped to
    a driver.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured — set it in .env to run migrations (the "
            "direct Postgres connection string from the Supabase project's Database "
            "settings, not the SUPABASE_URL/SUPABASE_KEY REST API credentials)."
        )
    url = settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: emit SQL to stdout, no live DB connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: connect to the database and apply them."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
