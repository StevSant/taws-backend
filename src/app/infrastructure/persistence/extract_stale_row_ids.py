from typing import Any, cast


def extract_stale_row_ids(rows: Any, keep: int) -> list[str]:
    """Return the `id`s of every row past the newest `keep`, for a retention prune (issue #29).

    `rows` is a PostgREST response's `.data`, ordered `created_at desc` by the caller — so
    slicing off the first `keep` leaves exactly the rows to delete. Typed `Any` and cast, same
    as the row mappers: `supabase-py` types `.data` as a broad JSON union that pyright can't
    subscript, and the shape is guaranteed by the `select("id")` the caller just issued.

    `keep` is clamped at 0 so a negative retention setting can't turn a prune into a
    delete-everything (a misconfigured `ANALYSIS_RETENTION_KEEP=-1` would otherwise wipe the
    table).
    """
    return [cast(str, row["id"]) for row in rows[max(keep, 0) :]]
