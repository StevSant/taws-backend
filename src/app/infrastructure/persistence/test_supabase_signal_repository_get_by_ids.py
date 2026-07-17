"""Unit tests for `SupabaseSignalRepository.get_by_ids` (batch signal lookup).

Briefing read/export paths resolve every linked signal id; the old shape was one
`get(id)` round trip per id. `get_by_ids` must batch that into a single
`.in_("id", [...])` query, key the result by signal id, silently omit missing ids,
and never hit the network for empty input.

Per `backend/CLAUDE.md`: minimal targeted tests next to the code under test.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.infrastructure.persistence.supabase_signal_repository import SupabaseSignalRepository

_CREATED_AT = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _row(signal_id: str, symbol: str) -> dict[str, Any]:
    return {
        "id": signal_id,
        "instrument_symbol": symbol,
        "impact_class": "positive",
        "confidence": 0.8,
        "evidence": [],
        "disclaimer": "not personalized advice",
        "locale": "en",
        "thesis": "thesis",
        "created_at": _CREATED_AT.isoformat(),
    }


class _FakeQuery:
    """Records the `.select().in_().execute()` chain the adapter is expected to run."""

    def __init__(self, rows: list[dict[str, Any]], in_calls: list[tuple[str, list[str]]]) -> None:
        self._rows = rows
        self._in_calls = in_calls

    def select(self, columns: str) -> "_FakeQuery":
        return self

    def in_(self, column: str, values: list[str]) -> "_FakeQuery":
        self._in_calls.append((column, list(values)))
        return self

    async def execute(self) -> SimpleNamespace:
        matched_ids = self._in_calls[-1][1]
        return SimpleNamespace(data=[row for row in self._rows if row["id"] in matched_ids])


class _FakeClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.table_calls: list[str] = []
        self.in_calls: list[tuple[str, list[str]]] = []

    def table(self, name: str) -> _FakeQuery:
        self.table_calls.append(name)
        return _FakeQuery(self._rows, self.in_calls)


class _FakeClientCache:
    """Stands in for `SupabaseClientCache`; counts how often a client is requested."""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client
        self.get_calls = 0

    async def get(self) -> _FakeClient:
        self.get_calls += 1
        return self._client


def _build_repository(rows: list[dict[str, Any]]) -> tuple[SupabaseSignalRepository, _FakeClient]:
    repository = SupabaseSignalRepository(supabase_url=None, supabase_key=None)
    client = _FakeClient(rows)
    repository._clients = _FakeClientCache(client)  # type: ignore[assignment]
    return repository, client


async def test_get_by_ids_returns_found_signals_keyed_by_id_in_one_query() -> None:
    repository, client = _build_repository([_row("sig-1", "AAPL"), _row("sig-2", "MSFT")])

    result = await repository.get_by_ids(["sig-1", "sig-2", "sig-gone"])

    assert set(result) == {"sig-1", "sig-2"}
    assert result["sig-1"].instrument_symbol == "AAPL"
    assert result["sig-2"].instrument_symbol == "MSFT"
    # One batched query, not one per id.
    assert client.table_calls == ["signals"]
    assert client.in_calls == [("id", ["sig-1", "sig-2", "sig-gone"])]


async def test_get_by_ids_missing_ids_are_absent_not_an_error() -> None:
    repository, _client = _build_repository([_row("sig-1", "AAPL")])

    result = await repository.get_by_ids(["sig-gone"])

    assert result == {}


async def test_get_by_ids_empty_input_returns_empty_dict_without_a_query() -> None:
    repository, client = _build_repository([_row("sig-1", "AAPL")])

    result = await repository.get_by_ids([])

    assert result == {}
    assert client.table_calls == []
