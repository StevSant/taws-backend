"""telegram_links atomic relink trigger (concurrent-link race backstop)

Adds a `BEFORE INSERT` trigger on `telegram_links` enforcing the "unlink-then-relink"
invariant documented in `TelegramLink`'s docstring and `TelegramLinkRepository.link`'s
docstring — at most one row per `user_id` and at most one row per `telegram_chat_id` —
as a DB-level backstop against a race in `SupabaseTelegramLinkRepository.link()`
(issue #14): that method performed the unlink-then-relink as THREE independent
PostgREST HTTP calls (delete-by-user_id, delete-by-chat_id, insert), each its own
auto-committing transaction. Two near-simultaneous `/start <token>` deliveries for
DIFFERENT users targeting the SAME `chat_id` (e.g. a leaked/shared token, or two people
linking from one device) could interleave those six statements so one caller's
just-inserted row is deleted by the other caller's concurrent delete-by-chat_id call —
silently, with no error surfaced to either caller.

Same pattern as migration `0002_review_states_transition_trigger` (issue #4's TOCTOU
backstop): move the "read stale state, then delete/insert it" logic from multiple
separate app-layer calls into a single atomic DB-side operation, guarded by
`pg_advisory_xact_lock` so concurrent inserts that could race on the SAME key are
serialized instead of interleaved.

Unlike `0002` (a single composite key, `entity_type || ':' || entity_id`),
`telegram_links` has TWO independent unique constraints — `user_id` and
`telegram_chat_id` — either of which a concurrent insert can collide on (the reported
race is same `telegram_chat_id`, different `user_id`; the symmetric case, same
`user_id`, different `telegram_chat_id`, e.g. one user linking from two devices near-
simultaneously, is the same class of bug). So this trigger acquires an advisory lock for
BOTH keys, always in a fixed lexicographic order (`user_id` before `telegram_chat_id`,
or vice versa, whichever sorts first as text) before touching the table — locking only
one of the two keys would leave the other race unprotected, and acquiring them in a
data-dependent (rather than fixed) order would deadlock two concurrent inserts that
each hold one key and wait on the other.

`SupabaseTelegramLinkRepository.link()` no longer performs the two `delete` calls
itself — this trigger's `delete ... where user_id = new.user_id or telegram_chat_id =
new.telegram_chat_id` (executed inside the SAME transaction as the triggering insert,
under the advisory lock) replaces them atomically.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- enforce_telegram_link_atomic_relink — BEFORE INSERT trigger function on
-- telegram_links.
--
-- Atomically removes any prior row for the same user_id OR the same
-- telegram_chat_id before allowing the new row to be inserted, replacing the
-- app-layer delete-then-delete-then-insert (three separate PostgREST calls) with one
-- atomic DB-side operation. pg_advisory_xact_lock is acquired for BOTH the user_id and
-- telegram_chat_id keys (fixed lexicographic order, to avoid deadlocking two
-- concurrent inserts that each hold one key and wait on the other) so a second
-- concurrent insert racing on either key blocks until the first commits, then
-- re-derives "any prior row for these keys" from the table itself rather than from a
-- value read before the lock was acquired.
-- =============================================================================
create or replace function public.enforce_telegram_link_atomic_relink()
returns trigger as $$
declare
    lock_key_first text;
    lock_key_second text;
begin
    if new.user_id::text < new.telegram_chat_id then
        lock_key_first := new.user_id::text;
        lock_key_second := new.telegram_chat_id;
    else
        lock_key_first := new.telegram_chat_id;
        lock_key_second := new.user_id::text;
    end if;

    perform pg_advisory_xact_lock(hashtextextended('telegram_link:' || lock_key_first, 0));
    perform pg_advisory_xact_lock(hashtextextended('telegram_link:' || lock_key_second, 0));

    delete from public.telegram_links
    where user_id = new.user_id or telegram_chat_id = new.telegram_chat_id;

    return new;
end;
$$ language plpgsql;

create trigger telegram_links_enforce_atomic_relink
    before insert on public.telegram_links
    for each row
    execute function public.enforce_telegram_link_atomic_relink();
"""

_DOWNGRADE_SQL = """
drop trigger if exists telegram_links_enforce_atomic_relink on public.telegram_links;
drop function if exists public.enforce_telegram_link_atomic_relink();
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
