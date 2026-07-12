"""MEDIUM fix (post-hoc adversarial review): `SupabaseWatchlistRepository.
list_for_user` must apply a stable `.order(...)` clause so the router's
`existing[0]` (used by `_resolve_owned_watchlist_id` to pick the caller's
"default" watchlist) is deterministic instead of depending on whatever order
Postgres/PostgREST happens to return rows in.
"""

from typing import Any

from app.infrastructure.persistence.supabase_watchlist_repository import (
    SupabaseWatchlistRepository,
)

_ROWS = [
    {
        "id": "wl-2",
        "user_id": "user-1",
        "name": "Second Watchlist",
        "created_at": "2026-01-02T00:00:00+00:00",
    },
    {
        "id": "wl-1",
        "user_id": "user-1",
        "name": "My Watchlist",
        "created_at": "2026-01-01T00:00:00+00:00",
    },
]


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: "_FakeTable", data: list[dict[str, Any]]) -> None:
        self._table = table
        self._data = data

    def select(self, columns: str = "*") -> "_FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeQuery":
        self._table.order_calls.append({"column": column, "desc": desc})
        return self

    async def execute(self) -> _FakeResponse:
        return _FakeResponse(self._data)


class _FakeTable:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        self.order_calls: list[dict[str, Any]] = []

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


async def test_list_for_user_applies_a_stable_order_clause() -> None:
    repo, fake_client = _repo_with_fake_client(_ROWS)

    watchlists = await repo.list_for_user("user-1")

    table = fake_client.tables["watchlists"]
    assert len(table.order_calls) >= 1
    assert table.order_calls[0]["column"] in {"created_at", "id"}
    assert len(watchlists) == 2
