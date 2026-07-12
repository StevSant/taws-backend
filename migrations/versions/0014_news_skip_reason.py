"""news_items.skip_reason (why an item produced no signal)

Issue #26: `news_items.analysis_status` alone can't explain *why* an article produced no
`Signal`. `skipped` collapses a deliberate cost decision (the pre-filter gated it), a
near-duplicate wire story, and an article that names no instrument at all into one opaque
state; `pending` collapses "nothing has looked at it yet" with "we tried and it didn't clear
the evidence floor". The news-detail page could therefore only render a bare "No se produjo
ninguna señal para esta noticia" — which reads as broken, not as an intentional decision — and
the Radar timeline showed all of them as the same ambiguous "Sin clasificar" tag (issue #68).

Adds a nullable `skip_reason` alongside `analysis_status`. NULL means "no reason to give":
either the item was `analyzed`, or it is `pending` and untouched. Written by
`AnalyzePendingNews` (batch) and `ForceAnalyzeNewsItem` (the manual "Analizar ahora" trigger,
issue #27); read by `GET /api/v1/news[/{id}]` via `NewsItemResponse.skip_reason`.

Mirrors `analysis_status`'s own modeling choice from migration 0009 — a plain `text` column
constrained by a `check`, not a Postgres enum — the same "app-layer enum, DB-layer check
constraint" call `review_states.state` (0002) and `scenario_monitors.status` (0008) make.
Adding a reason later is a one-line `check` change, not an `ALTER TYPE`. The values must stay
in sync with `NewsSkipReason` (`src/app/domain/market/entities/news_skip_reason.py`).

Retryability is carried by `analysis_status`, not by this column: `insufficient_evidence` and
`analysis_failed` are recorded against a row that stays `pending` (so the next batch run picks
it up again), while the other four are recorded against a `skipped` row (terminal).

No index: `skip_reason` is only ever read back on rows already fetched by id or by the existing
`news_items_pending_idx` — it is never itself a query predicate. No RLS change either; the
table's policy from 0009 is column-agnostic.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.news_items
    add column if not exists skip_reason text;

-- Values must stay in sync with the NewsSkipReason enum (domain/market/entities).
alter table public.news_items
    drop constraint if exists news_items_skip_reason_check;

alter table public.news_items
    add constraint news_items_skip_reason_check check (
        skip_reason is null or skip_reason in (
            'no_linked_instrument',
            'gated_low_relevance',
            'near_duplicate',
            'compliance_blocked',
            'insufficient_evidence',
            'analysis_failed'
        )
    );

comment on column public.news_items.skip_reason is
    'Why this item produced no Signal (NewsSkipReason). NULL when analyzed, or pending and '
    'untouched. Pairs with analysis_status: insufficient_evidence/analysis_failed stay '
    'pending (retried), the rest are skipped (terminal).';
"""

_DOWNGRADE_SQL = """
alter table public.news_items
    drop constraint if exists news_items_skip_reason_check;

alter table public.news_items
    drop column if exists skip_reason;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
