# Migrations

Managed by [Alembic](https://alembic.sqlalchemy.org/), driven from `backend/alembic.ini`
(`script_location = migrations`). Revisions live in `migrations/versions/`, applied in
dependency order (`down_revision` chain), tracked in the target database's
`alembic_version` table.

**No SQLAlchemy ORM models / autogenerate.** The app's runtime data layer is
`supabase-py` (PostgREST) — see `src/app/infrastructure/persistence/` — not SQLAlchemy.
Alembic is used purely as a raw-SQL migration *runner* (versioning + `upgrade`/
`downgrade` + the `alembic_version` table), not an ORM. Every revision is hand-written
SQL wrapped in `op.execute(...)` (see `migrations/versions/0001_watchlists_signals_briefings.py`).
`alembic revision --autogenerate` will not detect schema changes — always write
revisions by hand.

The connection string is resolved from `Settings.database_url` (`.env`) inside
`migrations/env.py`, never hardcoded in `alembic.ini` — so credentials never end up in
a committed file. Set `DATABASE_URL` to the **direct Postgres connection string** from
the Supabase project's *Database* settings (not the `SUPABASE_URL`/`SUPABASE_KEY` REST
API credentials used elsewhere).

## Applying migrations

### Supabase (recommended, matches production/staging)

```bash
uv run alembic upgrade head
```

Requires `DATABASE_URL` set in `.env`. Confirm the new tables appear under **Table
Editor** in the Supabase dashboard, and that **Authentication → Policies** shows the
RLS policies created by the migration.

### Local / offline dev (docker-compose Postgres)

The root `docker-compose.yml` (service `postgres`, `pgvector/pg16` image) is for
working without network access to Supabase. It has no `auth` schema, so `auth.users`
FKs and `auth.uid()` calls in these migrations fail as-is against it — this path is
meant for application-layer development against `public.*` tables, not a full Supabase
Auth replica.

```bash
DATABASE_URL="postgresql://taws:taws@localhost:5432/taws" uv run alembic upgrade head
```

## Common commands

```bash
uv run alembic upgrade head          # apply every pending revision
uv run alembic downgrade -1          # roll back one revision
uv run alembic current               # show the revision currently applied
uv run alembic history               # list all revisions in order
uv run alembic revision -m "<name>"  # scaffold a new empty revision (write the SQL by hand)
```

## Revisions

| Revision | Adds |
|----------|------|
| `0001_watchlists_signals_briefings` | `watchlists`, `watchlist_items`, `signals`, `briefings`, `review_states` + RLS policies |
| `0002_review_states_transition_trigger` | `BEFORE INSERT` trigger on `review_states` enforcing the review state machine (REVIEWED/DISCARDED terminal) as a DB-level backstop against a concurrent-request TOCTOU race, via `pg_advisory_xact_lock` |
| `0003_historical_analogs` | `vector` extension + `historical_analogs` table (pgvector RAG store for issue #15's historical-analogs retrieval) + RLS policy |
| `0004_telegram_links` | `telegram_links` (user_id <-> telegram_chat_id, unique on both) + `telegram_link_tokens` (short-lived `/start <token>` linking tokens) + RLS policies, for issue #14's Telegram per-user linking and Watchdog alert delivery |
