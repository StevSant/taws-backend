"""Optional note target: link a note to a briefing, scenario, or instrument.

`target_kind` + `target_label` are the DURABLE PAIR — they outlive the target's
deletion. The FK column is the LIVENESS BIT: `on delete set null` clears it when the
target dies, so (kind set, FK null) means "this note's target is gone" and the API
reports `available: false`. This deliberately inherits the pattern
`news_items.signal_id` already uses (0009), and avoids the one
`briefings.linked_signal_ids` uses (a bare uuid[] with no FK, which is why briefing
chips dangle into "Señal archivada").

`target_watchlist_id` is a link-building hint for briefings only: `/briefings` renders
only the ACTIVE watchlist's reports, so a deep link must pre-select the right list.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.user_notes
    add column if not exists target_kind text,
    add column if not exists briefing_id uuid,
    add column if not exists scenario_id uuid,
    add column if not exists instrument_symbol text,
    add column if not exists target_watchlist_id uuid,
    add column if not exists target_label text;

-- Foreign keys: `set null` on delete makes each FK a liveness bit. Instruments have no
-- delete path (symbol is a PK, the catalog repo exposes only upsert/all_rows), so that
-- one needs no delete action.
alter table public.user_notes
    drop constraint if exists user_notes_briefing_id_fkey;
alter table public.user_notes
    add constraint user_notes_briefing_id_fkey
    foreign key (briefing_id) references public.briefings (id) on delete set null;

alter table public.user_notes
    drop constraint if exists user_notes_scenario_id_fkey;
alter table public.user_notes
    add constraint user_notes_scenario_id_fkey
    foreign key (scenario_id) references public.scenarios (id) on delete set null;

alter table public.user_notes
    drop constraint if exists user_notes_instrument_symbol_fkey;
alter table public.user_notes
    add constraint user_notes_instrument_symbol_fkey
    foreign key (instrument_symbol) references public.instruments (symbol);

alter table public.user_notes
    drop constraint if exists user_notes_target_watchlist_id_fkey;
alter table public.user_notes
    add constraint user_notes_target_watchlist_id_fkey
    foreign key (target_watchlist_id) references public.watchlists (id) on delete set null;

-- Kind and label are the durable pair: both present, or both absent.
alter table public.user_notes
    drop constraint if exists user_notes_kind_label_pair;
alter table public.user_notes
    add constraint user_notes_kind_label_pair check (
        (target_kind is null and target_label is null)
     or (target_kind is not null and target_label is not null)
    );

-- The live FK must match the kind. All FKs null while kind is set = the target died.
alter table public.user_notes
    drop constraint if exists user_notes_target_kind_matches;
alter table public.user_notes
    add constraint user_notes_target_kind_matches check (
        (target_kind is null
            and briefing_id is null
            and scenario_id is null
            and instrument_symbol is null
            and target_watchlist_id is null)
     or (target_kind = 'briefing'
            and scenario_id is null
            and instrument_symbol is null)
     or (target_kind = 'scenario'
            and briefing_id is null
            and instrument_symbol is null
            and target_watchlist_id is null)
     or (target_kind = 'instrument'
            and briefing_id is null
            and scenario_id is null
            and target_watchlist_id is null)
    );

create index if not exists user_notes_user_kind_idx
    on public.user_notes (user_id, target_kind);
"""

_DOWNGRADE_SQL = """
drop index if exists user_notes_user_kind_idx;

alter table public.user_notes
    drop constraint if exists user_notes_target_kind_matches;
alter table public.user_notes
    drop constraint if exists user_notes_kind_label_pair;
alter table public.user_notes
    drop constraint if exists user_notes_target_watchlist_id_fkey;
alter table public.user_notes
    drop constraint if exists user_notes_instrument_symbol_fkey;
alter table public.user_notes
    drop constraint if exists user_notes_scenario_id_fkey;
alter table public.user_notes
    drop constraint if exists user_notes_briefing_id_fkey;

alter table public.user_notes
    drop column if exists target_label,
    drop column if exists target_watchlist_id,
    drop column if exists instrument_symbol,
    drop column if exists scenario_id,
    drop column if exists briefing_id,
    drop column if exists target_kind;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
