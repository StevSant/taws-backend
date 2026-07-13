"""Migration `0012_instruments`: seeds `public.instruments` from the packaged universe.

Requires `DATABASE_URL` pointing at a reachable Postgres (docker-compose `postgres`
service works for this table — it has no `auth.users` FK, unlike earlier revisions).
Skipped automatically when `DATABASE_URL` isn't configured (e.g. CI without a live DB),
consistent with this project's "no live DB in CI" migration testing stance
(`migrations/README.md`, `tests/test_alembic_single_head.py`).
"""

import logging
import os

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Requires a live Postgres reachable via DATABASE_URL to run alembic upgrade/downgrade.",
)

_BACKEND_ROOT = __file__.rsplit("/tests/", 1)[0]


def _alembic_config() -> Config:
    config = Config(f"{_BACKEND_ROOT}/alembic.ini")
    config.set_main_option("script_location", f"{_BACKEND_ROOT}/migrations")
    return config


def _engine() -> sqlalchemy.Engine:
    get_settings.cache_clear()
    url = get_settings().database_url
    assert url is not None
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return sqlalchemy.create_engine(url)


@pytest.fixture
def migrated_db() -> sqlalchemy.Engine:
    # `migrations/env.py` calls `logging.config.fileConfig(...)` at import time
    # (alembic's own convention), which — with `alembic.ini`'s explicit `[loggers]`
    # section not listing every app logger — disables loggers it doesn't know
    # about (`disable_existing_loggers` defaults to `True`). That would otherwise
    # leak into unrelated tests asserting on `caplog` (e.g.
    # `test_startup_auth_guard.py`) that run later in the same session. Snapshot
    # and restore every logger's `disabled` flag around the alembic calls so this
    # test file stays a no-op for global logging state.
    manager = logging.Logger.manager
    previously_disabled = {
        name: logger.disabled
        for name, logger in manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }

    config = _alembic_config()
    command.upgrade(config, "0015")
    engine = _engine()
    try:
        yield engine
    finally:
        command.downgrade(config, "0014")
        engine.dispose()
        for name, logger in manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                logger.disabled = previously_disabled.get(name, logger.disabled)


def test_upgrade_seeds_exactly_27_rows(migrated_db: sqlalchemy.Engine) -> None:
    with migrated_db.connect() as conn:
        count = conn.execute(sqlalchemy.text("select count(*) from public.instruments")).scalar()

    assert count == 27


def test_rerunning_seed_insert_is_a_no_op(migrated_db: sqlalchemy.Engine) -> None:
    with migrated_db.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "insert into public.instruments "
                "(symbol, name, asset_class, currency, coingecko_id, yfinance_symbol, source) "
                "values ('AAPL', 'Apple Inc.', 'stock', 'USD', null, null, 'seed') "
                "on conflict (symbol) do nothing"
            )
        )

    with migrated_db.connect() as conn:
        count = conn.execute(sqlalchemy.text("select count(*) from public.instruments")).scalar()

    assert count == 27


def test_downgrade_drops_the_table(migrated_db: sqlalchemy.Engine) -> None:
    config = _alembic_config()
    command.downgrade(config, "0014")

    with migrated_db.connect() as conn:
        exists = conn.execute(
            sqlalchemy.text(
                "select exists (select 1 from information_schema.tables "
                "where table_schema = 'public' and table_name = 'instruments')"
            )
        ).scalar()

    assert exists is False

    command.upgrade(config, "0015")


def test_alembic_heads_includes_0015() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()

    assert heads == ["0015"]
