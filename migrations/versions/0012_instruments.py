"""instruments

Global, DB-backed instrument catalog (issue: Instruments Catalog Slice 1). Replaces
the packaged `universe.json` as the runtime source of truth for the tradable
instrument universe with a shared `public.instruments` table, seeded from the same
27 rows `universe.json` carried (including the `coingecko_id`/`yfinance_symbol`
vendor-id overrides).

Like `public.signals` (0001), this is a shared, read-mostly catalog: RLS is enabled
with a single `select` policy scoped to `authenticated`, and no insert/update/delete
policy — writes only succeed through the Supabase service-role key, which bypasses
RLS entirely. Regular users (and future user-submitted registrations, Slice 2) never
write to this table directly from the client.

See:
    docs/specs/2026-07-11-taws-hackathon-architecture-design.md
    openspec/changes/instruments-catalog/design.md

Revision ID: 0012
Revises: 0011b
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- instruments — the global, user-extensible tradable instrument catalog.
--
-- Shared, read-mostly data: not user-owned (unlike watchlists), so RLS mirrors
-- `signals` (0001) rather than `watchlists` — one authenticated select policy, no
-- write policy for any role, so writes only succeed via the service-role key.
-- =============================================================================
create table if not exists public.instruments (
    symbol text primary key,
    name text not null,
    asset_class text not null
        check (asset_class in ('stock', 'crypto', 'credit', 'commodity', 'forex')),
    currency text not null default 'USD',
    coingecko_id text,
    yfinance_symbol text,
    source text not null default 'user' check (source in ('seed', 'user')),
    created_at timestamptz not null default now()
);

create index if not exists instruments_asset_class_idx on public.instruments (asset_class);

alter table public.instruments enable row level security;

create policy "instruments_select_authenticated" on public.instruments
    for select using (auth.role() = 'authenticated');

-- Seed: all 27 rows from the packaged `universe.json`, embedded as a literal
-- insert (no `app.*` import at migration time — see the sqlalchemy-alembic
-- migration convention of hand-written SQL only, no autogenerate). Idempotent via
-- `on conflict (symbol) do nothing`, so replaying this migration never duplicates
-- or mutates existing rows.
insert into public.instruments
    (symbol, name, asset_class, currency, coingecko_id, yfinance_symbol, source)
values
    ('AAPL', 'Apple Inc.', 'stock', 'USD', null, null, 'seed'),
    ('MSFT', 'Microsoft Corporation', 'stock', 'USD', null, null, 'seed'),
    ('NVDA', 'NVIDIA Corporation', 'stock', 'USD', null, null, 'seed'),
    ('TSLA', 'Tesla Inc.', 'stock', 'USD', null, null, 'seed'),
    ('AMZN', 'Amazon.com Inc.', 'stock', 'USD', null, null, 'seed'),
    ('GOOGL', 'Alphabet Inc.', 'stock', 'USD', null, null, 'seed'),
    ('META', 'Meta Platforms Inc.', 'stock', 'USD', null, null, 'seed'),
    ('JPM', 'JPMorgan Chase & Co.', 'stock', 'USD', null, null, 'seed'),
    ('PLTR', 'Palantir Technologies Inc.', 'stock', 'USD', null, null, 'seed'),
    ('AMD', 'Advanced Micro Devices Inc.', 'stock', 'USD', null, null, 'seed'),
    ('AVGO', 'Broadcom Inc.', 'stock', 'USD', null, null, 'seed'),
    ('NFLX', 'Netflix Inc.', 'stock', 'USD', null, null, 'seed'),
    ('COIN', 'Coinbase Global Inc.', 'stock', 'USD', null, null, 'seed'),
    ('MSTR', 'MicroStrategy Incorporated', 'stock', 'USD', null, null, 'seed'),
    ('SPY', 'SPDR S&P 500 ETF Trust', 'stock', 'USD', null, null, 'seed'),
    ('QQQ', 'Invesco QQQ Trust', 'stock', 'USD', null, null, 'seed'),
    ('BTC', 'Bitcoin', 'crypto', 'USD', 'bitcoin', null, 'seed'),
    ('ETH', 'Ethereum', 'crypto', 'USD', 'ethereum', null, 'seed'),
    ('SOL', 'Solana', 'crypto', 'USD', 'solana', null, 'seed'),
    ('BNB', 'BNB', 'crypto', 'USD', 'binancecoin', null, 'seed'),
    ('XRP', 'XRP', 'crypto', 'USD', 'ripple', null, 'seed'),
    ('LQD', 'iShares iBoxx $ Investment Grade Corporate Bond ETF', 'credit', 'USD',
        null, null, 'seed'),
    ('HYG', 'iShares iBoxx $ High Yield Corporate Bond ETF', 'credit', 'USD', null, null, 'seed'),
    ('TLT', 'iShares 20+ Year Treasury Bond ETF', 'credit', 'USD', null, null, 'seed'),
    ('GLD', 'SPDR Gold Shares', 'commodity', 'USD', null, null, 'seed'),
    ('USO', 'United States Oil Fund', 'commodity', 'USD', null, null, 'seed'),
    ('EURUSD', 'Euro / US Dollar', 'forex', 'USD', null, 'EURUSD=X', 'seed')
on conflict (symbol) do nothing;
"""

_DOWNGRADE_SQL = """
drop table if exists public.instruments cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
