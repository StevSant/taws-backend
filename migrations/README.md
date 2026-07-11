# Migrations

Plain `.sql` files, applied in filename order. There is no Supabase CLI or ORM
migration tooling wired into this repo yet (no `supabase/` dir, no Alembic) — these
are hand-written, idempotent-where-practical (`if not exists`) migrations meant to be
run once against the target database.

## Applying a migration

### Supabase (recommended, matches production/staging)

1. Open the project's **SQL Editor** in the Supabase dashboard.
2. Paste the contents of the migration file and run it.
3. Confirm the new tables appear under **Table Editor**, and that **Authentication →
   Policies** shows the RLS policies created by the migration.

### Local / offline dev (docker-compose Postgres)

The root `docker-compose.yml` (service `postgres`, `pgvector/pg16` image) is for
working without network access to Supabase. It has no `auth` schema, so
`auth.users` FKs and `auth.uid()` calls in these migrations will fail as-is against
it — this path is meant for application-layer development against `public.*`
tables, not a full Supabase Auth replica. Run:

```bash
psql "postgresql://taws:taws@localhost:5432/taws" -f migrations/0001_watchlists_signals_briefings.sql
```

## Migrations

| File | Adds |
|------|------|
| `0001_watchlists_signals_briefings.sql` | `watchlists`, `watchlist_items`, `signals`, `briefings`, `review_states` + RLS policies |
