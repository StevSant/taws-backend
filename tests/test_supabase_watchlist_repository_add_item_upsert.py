"""`SupabaseWatchlistRepository.add_item` becomes an idempotent upsert (FIX #4):
`on_conflict="watchlist_id,symbol"` + `ignore_duplicates=True`, then re-selects
the row so the return type stays a `WatchlistItem` even on a no-op conflict
(where `.upsert(...).execute()`'s own `.data` would otherwise be empty/stale).

Calling `add_item` twice for the same `(watchlist_id, symbol)` must not raise
and must not create a duplicate row (instrument-registration spec's "does not
duplicate the watchlist entry").
"""

from typing import Any

import pytest

from app.infrastructure.persistence.supabase_watchlist_repository import (
    SupabaseWatchlistRepository,
)

_ROW = {
    "id": "item-1",
    "watchlist_id": "wl-1",
    "symbol": "DOGE",
    "added_at": "2026-01-01T00:00:00+00:00",
}


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: "_FakeTable", data: list[dict[str, Any]]) -> None:
        self._table = table
        self._data = data
        self._filters: dict[str, Any] = {}

    def upsert(
        self,
        payload: dict[str, Any],
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> "_FakeQuery":
        self._table.upsert_calls.append(
            {"payload": payload, "on_conflict": on_conflict, "ignore_duplicates": ignore_duplicates}
        )
        return self

    def select(self, columns: str = "*") -> "_FakeQuery":
        self._table.select_calls += 1
        return self

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters[column] = value
        return self

    async def execute(self) -> _FakeResponse:
        return _FakeResponse(self._data)


class _FakeTable:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        self.upsert_calls: list[dict[str, Any]] = []
        self.select_calls = 0

    def upsert(
        self,
        payload: dict[str, Any],
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> _FakeQuery:
        return _FakeQuery(self, self._data).upsert(
            payload, on_conflict=on_conflict, ignore_duplicates=ignore_duplicates
        )

    def select(self, columns: str = "*") -> _FakeQuery:
        return _FakeQuery(self, self._data).select(columns)


class _FakeSupabaseClient:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.tables: dict[str, _FakeTable] = {}
        self._data = data

    def table(self, name: str) -> _FakeTable:
        if name not in self.tables:
            self.tables[name] = _FakeTable(self._data)
        return self.tables[name]


def _repo_with_fake_client(
    data: list[dict[str, Any]],
) -> tuple[SupabaseWatchlistRepository, _FakeSupabaseClient]:
    repo = SupabaseWatchlistRepository(
        supabase_url="https://x.supabase.co", supabase_key="sb_secret_x"
    )
    fake_client = _FakeSupabaseClient(data)

    async def _fake_get() -> _FakeSupabaseClient:
        return fake_client

    repo._clients.get = _fake_get  # type: ignore[method-assign]
    return repo, fake_client


async def test_add_item_upserts_with_on_conflict_watchlist_id_symbol() -> None:
    repo, fake_client = _repo_with_fake_client([_ROW])

    item = await repo.add_item("wl-1", "DOGE")

    table = fake_client.tables["watchlist_items"]
    assert len(table.upsert_calls) == 1
    assert table.upsert_calls[0]["on_conflict"] == "watchlist_id,symbol"
    assert table.upsert_calls[0]["ignore_duplicates"] is True
    assert item.watchlist_id == "wl-1"
    assert item.symbol == "DOGE"


async def test_add_item_reselects_the_row_after_a_no_op_conflict() -> None:
    """When the upsert itself is a no-op (ignore_duplicates), `.execute().data`
    can come back empty/stale for the conflicting row — the adapter must
    re-select by (watchlist_id, symbol) so it can still return a `WatchlistItem`.
    """
    repo, fake_client = _repo_with_fake_client([_ROW])

    item = await repo.add_item("wl-1", "DOGE")

    table = fake_client.tables["watchlist_items"]
    assert table.select_calls >= 1
    assert item.id == "item-1"


async def test_add_item_called_twice_is_idempotent_no_duplicate_no_error() -> None:
    repo, fake_client = _repo_with_fake_client([_ROW])

    first = await repo.add_item("wl-1", "DOGE")
    second = await repo.add_item("wl-1", "DOGE")

    assert first.symbol == second.symbol == "DOGE"
    table = fake_client.tables["watchlist_items"]
    assert len(table.upsert_calls) == 2  # both calls succeed, no exception raised


async def test_add_item_raises_clear_error_when_reselect_finds_no_row() -> None:
    """LOW fix (post-hoc adversarial review): if the post-upsert re-select comes
    back empty (e.g. a stale read on eventual-consistency, or an RLS mismatch),
    the adapter must raise a clear error instead of `IndexError`-ing on
    `response.data[0]`, which would otherwise surface as an opaque 500."""
    repo, fake_client = _repo_with_fake_client([])

    with pytest.raises(LookupError, match="watchlist_items"):
        await repo.add_item("wl-1", "DOGE")
