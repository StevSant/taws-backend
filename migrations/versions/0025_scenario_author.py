"""scenarios.author_id — scope free-form scenario runs to their author.

Migration 0006 made `scenarios` a fully shared table: any authenticated user could read
every row. That is correct for PRESET runs ("Fed +50bp" is market research with no single
owner), but wrong for FREE-FORM runs — the user's own typed text lands in `title`/
`narrative`/`spec`, so a private "what if my employer is acquired and I'm laid off"
scenario was published to every account and surfaced under everyone's "Mis escenarios".

`author_id` splits the difference:

- Preset runs are inserted with `author_id = null` → still global/shared (and still
  cacheable per `(preset_id, locale)`).
- Free-form runs are inserted with `author_id = <the user>` → visible only to that user.

The backend reads `scenarios` with the service-role key (RLS is bypassed), so the real
enforcement is the `author_id is null or author_id = <user>` filter in
`SupabaseScenarioRepository.list_recent` plus the per-id ownership check in the
`GET /scenarios/{id}` router. The RLS policy below is defense-in-depth for any future
anon-key / PostgREST read path, matching the pattern every user-owned table already uses.

Existing rows keep `author_id = null` (the column is added nullable with no default), so
history stays visible as global — only NEW free-form runs are scoped.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.scenarios
    add column if not exists author_id uuid;

alter table public.scenarios
    drop constraint if exists scenarios_author_id_fkey;
alter table public.scenarios
    add constraint scenarios_author_id_fkey
    foreign key (author_id) references auth.users (id) on delete cascade;

create index if not exists scenarios_author_id_idx on public.scenarios (author_id);

-- Replace the "any authenticated user can read every row" policy with one that also
-- lets a reader see global rows (author_id null) and their own free-form rows only.
drop policy if exists "scenarios_select_authenticated" on public.scenarios;
drop policy if exists "scenarios_select_own_or_global" on public.scenarios;
create policy "scenarios_select_own_or_global" on public.scenarios
    for select using (
        auth.role() = 'authenticated'
        and (author_id is null or author_id = auth.uid())
    );
"""

_DOWNGRADE_SQL = """
drop policy if exists "scenarios_select_own_or_global" on public.scenarios;
create policy "scenarios_select_authenticated" on public.scenarios
    for select using (auth.role() = 'authenticated');

drop index if exists scenarios_author_id_idx;

alter table public.scenarios
    drop constraint if exists scenarios_author_id_fkey;
alter table public.scenarios
    drop column if exists author_id;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
