"""signal analysis fields (thesis, key_drivers, risk_factors, analysis_available)

Issue #40: surface a real AI analysis on each `Signal`. Extends `signals` (migration
0001) with the Analyst's actual analytical output instead of just an impact class +
one-line reasoning:

- `thesis` — a 3-5 sentence analytical thesis (text, defaults to '').
- `key_drivers` — the concrete factors driving the call (text[], defaults to '{}').
- `risk_factors` — what would invalidate the call (text[], defaults to '{}').
- `analysis_available` — False when classification fell back to an uncertain/zero-
  confidence call (no LLM key / unparseable response); the frontend labels those
  "análisis no disponible" rather than rendering an empty thesis as real analysis.
  Defaults to true so rows predating this migration read as real analyses.

Same ownership/RLS model as the base `signals` table — no policy change needed here.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.signals
    add column if not exists thesis text not null default '',
    add column if not exists key_drivers text[] not null default '{}',
    add column if not exists risk_factors text[] not null default '{}',
    add column if not exists analysis_available boolean not null default true;
"""

_DOWNGRADE_SQL = """
alter table public.signals
    drop column if exists analysis_available,
    drop column if exists risk_factors,
    drop column if exists key_drivers,
    drop column if exists thesis;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
