"""review_states transition trigger (TOCTOU backstop)

Adds a `BEFORE INSERT` trigger on `review_states` enforcing the same state machine
documented in `src/app/application/review/review_transition_policy.py` (REVIEWED and
DISCARDED are terminal; ESCALATED is not) as a DB-level backstop against a
check-then-insert race in `SubmitReviewDecision.execute()` (issue #4): two concurrent
`POST .../reviews` requests on the same entity can both read the same "current latest
decision" via `list_review_states()` before either insert completes, both pass the
app-layer `assert_transition_allowed()` check, and both insert — producing an illegal
sequence (e.g. a `discarded` row appended right after a `reviewed` row).

`pg_advisory_xact_lock` (not `select ... for update`) is used to serialize concurrent
inserts for the same `(entity_type, entity_id)` pair, because a row-level lock can't
protect the "no prior state yet" case — there is no row to lock before an entity's
very first review state exists. The advisory lock key is derived from
`entity_type || ':' || entity_id`, held only for the duration of the inserting
transaction, and released automatically at commit/rollback (the `_xact_lock` variant).

The app-layer `assert_transition_allowed()` check stays in place unchanged — it is
still the fast, friendly error path for the common (non-racing) case, giving a clean
error without a DB round-trip needed to explain it. This trigger is strictly the
correctness backstop for the race; `SubmitReviewDecision.execute()` catches the
Postgrest error this trigger raises and re-raises it as the same
`IllegalReviewTransitionError` the app-layer check raises, so the router's existing
`409` handling covers both paths uniformly.

The trigger also overwrites `new.created_at` with `clock_timestamp()` immediately
after acquiring the advisory lock, making the DB — not the client — authoritative for
ordering. `ReviewState.created_at` is stamped in Python at construction time
(`domain/review/entities/review_state.py`), before the request reaches this lock, so
it does not reflect true insert/commit order under concurrent request latency: a
slower request can still acquire the lock and commit later while carrying an earlier
client-side timestamp than a faster request that already committed. Left unfixed,
`ORDER BY created_at DESC LIMIT 1` — both this trigger's own re-derivation and every
app-layer "latest state" read (`SupabaseSignalRepository`/`SupabaseBriefingRepository`)
— can pick the wrong row as "latest", silently defeating the very invariant this
migration exists to protect. Overwriting `created_at` with `clock_timestamp()` right
after the lock is acquired guarantees it is monotonically increasing in true
lock-acquisition (and therefore commit) order per `(entity_type, entity_id)`, since a
second concurrent request cannot acquire the lock — and therefore cannot evaluate
`clock_timestamp()` here — until the first has committed and released it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- enforce_review_transition — BEFORE INSERT trigger function on review_states.
--
-- Re-derives the entity's latest decision from the table itself at insert time
-- (never from a value the inserting transaction read earlier) and rejects the
-- insert if that latest decision is terminal (reviewed/discarded).
-- pg_advisory_xact_lock serializes concurrent inserts for the same
-- (entity_type, entity_id): a second concurrent request blocks until the first
-- commits, then re-reads the now-current latest decision and is correctly
-- rejected if the first request just terminated the entity.
--
-- Correctness of the re-derivation below assumes READ COMMITTED isolation
-- (Postgres/Supabase default): each statement inside this trigger sees rows
-- committed as of that statement's start, so the SELECT below observes any row
-- committed by a prior lock holder before this transaction acquired the lock.
-- =============================================================================
create or replace function public.enforce_review_transition()
returns trigger as $$
declare
    latest_decision text;
begin
    perform pg_advisory_xact_lock(
        hashtextextended(new.entity_type || ':' || new.entity_id::text, 0)
    );

    -- The trigger, not the client, is authoritative for `created_at` ordering — see
    -- the module docstring above for why the client-stamped timestamp can't be
    -- trusted. Evaluating clock_timestamp() here, immediately after acquiring the
    -- per-entity advisory lock and before re-deriving "latest", guarantees this
    -- column is monotonically increasing in true lock-acquisition/commit order.
    new.created_at := clock_timestamp();

    select decision into latest_decision
    from public.review_states
    where entity_type = new.entity_type and entity_id = new.entity_id
    order by created_at desc
    limit 1;

    if latest_decision in ('reviewed', 'discarded') then
        raise exception
            'illegal_review_transition: % % is already in terminal state %',
            new.entity_type, new.entity_id, latest_decision
            using errcode = 'P0001';
    end if;

    return new;
end;
$$ language plpgsql;

create trigger review_states_enforce_transition
    before insert on public.review_states
    for each row
    execute function public.enforce_review_transition();
"""

_DOWNGRADE_SQL = """
drop trigger if exists review_states_enforce_transition on public.review_states;
drop function if exists public.enforce_review_transition();
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
