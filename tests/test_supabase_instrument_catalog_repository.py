"""`SupabaseInstrumentCatalogRepository`: Supabase-backed `InstrumentCatalogRepository`.

Mirrors `SupabaseWatchlistRepository`'s client-cache + retry pattern. Exercised
against a fake `supabase-py` client (no network) — the adapter's job is building
the right `.table(...).upsert(...)`/`.select(...)` calls and mapping rows back to
`InstrumentRow`, not proving `supabase-py` itself works.
"""

from typing import Any

from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.infrastructure.persistence.supabase_instrument_catalog_repository import (
    SupabaseInstrumentCatalogRepository,
)

_ROW = {
    "symbol": "BTC",
    "name": "Bitcoin",
    "asset_class": "crypto",
    "currency": "USD",
    "coingecko_id": "bitcoin",
    "yfinance_symbol": None,
}


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    """Records the call chain and returns a canned response on `.execute()`."""

    def __init__(self, table: "_FakeTable", data: list[dict[str, Any]]) -> None:
        self._table = table
        self._data = data

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
        return self

    async def execute(self) -> _FakeResponse:
        return _FakeResponse(self._data)


class _FakeTable:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data
        self.upsert_calls: list[dict[str, Any]] = []

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
        return _FakeQuery(self, self._data)


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
) -> tuple[SupabaseInstrumentCatalogRepository, _FakeSupabaseClient]:
    repo = SupabaseInstrumentCatalogRepository(
        supabase_url="https://x.supabase.co", supabase_key="sb_secret_x"
    )
    fake_client = _FakeSupabaseClient(data)

    async def _fake_get() -> _FakeSupabaseClient:
        return fake_client

    repo._clients.get = _fake_get  # type: ignore[method-assign]
    return repo, fake_client


async def test_upsert_calls_supabase_with_on_conflict_symbol() -> None:
    repo, fake_client = _repo_with_fake_client([_ROW])
    row = InstrumentRow(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="bitcoin",
    )

    await repo.upsert(row)

    table = fake_client.tables["instruments"]
    assert len(table.upsert_calls) == 1
    assert table.upsert_calls[0]["on_conflict"] == "symbol"
    assert table.upsert_calls[0]["ignore_duplicates"] is True
    assert table.upsert_calls[0]["payload"]["symbol"] == "BTC"


async def test_all_rows_maps_rows_to_instrument_row() -> None:
    repo, _ = _repo_with_fake_client([_ROW])

    rows = await repo.all_rows()

    assert rows == [
        InstrumentRow(
            symbol="BTC",
            name="Bitcoin",
            asset_class=AssetClass.CRYPTO,
            currency="USD",
            coingecko_id="bitcoin",
            yfinance_symbol=None,
        )
    ]


async def test_all_rows_returns_empty_list_when_catalog_is_empty() -> None:
    repo, _ = _repo_with_fake_client([])

    rows = await repo.all_rows()

    assert rows == []
