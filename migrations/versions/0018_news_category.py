"""news_items.category — topical category, independent of signal impact

Adds the subject tag each article carries (issue #69): what the news is *about*, as opposed
to `signals.impact`, which says whether it is good or bad for an instrument. The two are
computed on independent paths — `classify_news_category` runs during ingest and needs no LLM
call — so an item is categorized even when it never produces a signal.

Nullable on purpose, with no default. Three states must stay distinguishable:

  * `null`           — no classifier has run over this row (every row that predates this
                       revision). `IngestNews`/`upsert_many` backfills these the next time the
                       article is fetched, guarded by `category is null` so a value already
                       there is never overwritten.
  * `'uncategorized'`— the classifier ran and could not place the item. An honest state, and
                       deliberately NOT the same thing as the impact bucket the UI shows as
                       "Sin clasificar".
  * anything else    — a real topic.

A `NOT NULL DEFAULT 'uncategorized'` would collapse the first two into each other and leave
old rows permanently, silently mislabelled as "we looked and found nothing".

The `check` constraint pins the taxonomy to the `NewsCategory` StrEnum. It is what lets
`news_item_row_mapper._category_from_row` treat an unknown value as "the DB is ahead of this
deploy" and degrade to `None` instead of 500-ing `GET /api/v1/news` mid-rolling-deploy.

The partial index serves the browse page's `category=` filter (`GET /api/v1/news/browse`),
mirroring the filter indexes 0016 added for the other facets. Partial (`where category is not
null`) because the null rows are exactly the ones no `category=` query can ever match.

Compliance note (HU3): `category` is descriptive metadata about an article. It carries no
buy/sell/order/quantity/price_target semantics, and must never be extended to.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.news_items
    add column if not exists category text;

alter table public.news_items
    drop constraint if exists news_items_category_check;

alter table public.news_items
    add constraint news_items_category_check
    check (category is null or category in (
        'macro',
        'earnings',
        'regulation',
        'crypto',
        'mergers_acquisitions',
        'geopolitics',
        'company_news',
        'uncategorized'
    ));

create index if not exists news_items_category_idx
    on public.news_items (category)
    where category is not null;
"""

_DOWNGRADE_SQL = """
drop index if exists news_items_category_idx;

alter table public.news_items
    drop constraint if exists news_items_category_check;

alter table public.news_items
    drop column if exists category;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
