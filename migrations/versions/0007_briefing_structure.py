"""briefings: instrument_breakdown, open_review_items

Track-5 T1 data layer: extends `public.briefings` with the fuller document structure
issue #16 adds on top of the T0 "basic" briefing (issue #3) — see
`src/app/domain/briefing/entities/briefing.py` for the full shape rationale:

- `instrument_breakdown` — one mini-section per watchlist instrument (narrative, impact
  classes, signal ids, evidence sources), JSONB same as `signals.evidence` (migration 0001).
- `open_review_items` — signals/prior briefings for this watchlist with no recorded
  reviewer decision yet, snapshotted at generation time. JSONB (entity_type + entity_id
  pairs), not a new relational table — this is a read-time projection over the existing
  `review_states` table (migration 0001), persisted here only so a past briefing's "what
  was still pending when this ran" view doesn't silently change as later reviews land.

No new column duplicates existing fields: `summary` already serves as the executive
summary, `linked_signal_ids` already covers linked signals/evidence — see the acceptance-
criteria mapping in the `Briefing` entity's docstring.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.briefings
    add column if not exists instrument_breakdown jsonb not null default '[]'::jsonb,
    add column if not exists open_review_items jsonb not null default '[]'::jsonb;
"""

_DOWNGRADE_SQL = """
alter table public.briefings
    drop column if exists open_review_items,
    drop column if exists instrument_breakdown;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
