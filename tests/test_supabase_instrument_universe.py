"""`SupabaseInstrumentUniverse`: DB-backed `InstrumentUniverse` adapter.

Async `create()` factory loads the whole catalog once (via a fake
`InstrumentCatalogRepository`, 27 fixture rows matching the real seed), then
`all()`/`by_symbol()`/`by_asset_class()` are plain in-memory reads — the SYNC port
contract is unchanged (instrument-catalog spec: "Port signature is unchanged").
`add()` (append-on-register, Slice 2) and `all_rows()` (sync vendor-id override
source for `get_market_data_provider`, FIX #7) are adapter-only extensions.
"""

import json
from pathlib import Path

import pytest

from app.domain.market.entities import Instrument, InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import InstrumentCatalogRepository
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse

_SEED_PATH = Path(__file__).resolve().parent.parent / "src/app/infrastructure/seeds/universe.json"


def _fixture_rows() -> list[InstrumentRow]:
    with _SEED_PATH.open(encoding="utf-8") as seed_file:
        raw_rows = json.load(seed_file)
    return [
        InstrumentRow(
            symbol=row["symbol"],
            name=row["name"],
            asset_class=AssetClass(row["asset_class"]),
            currency=row["currency"],
            coingecko_id=row.get("coingecko_id"),
            yfinance_symbol=row.get("yfinance_symbol"),
        )
        for row in raw_rows
    ]


class _FakeInstrumentCatalogRepository(InstrumentCatalogRepository):
    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows = list(rows)

    async def upsert(self, row: InstrumentRow) -> None:
        self._rows = [r for r in self._rows if r.symbol != row.symbol] + [row]

    async def all_rows(self) -> list[InstrumentRow]:
        return list(self._rows)


@pytest.fixture
def fixture_rows() -> list[InstrumentRow]:
    return _fixture_rows()


async def test_create_builds_the_index_from_the_repository(
    fixture_rows: list[InstrumentRow],
) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)

    universe = await SupabaseInstrumentUniverse.create(repo)

    assert len(universe.all()) == 27


async def test_create_raises_when_the_catalog_is_empty() -> None:
    """Empty catalog fails loud (never a silent-empty universe) — the accepted
    fail-loud contract: an unseeded/unavailable DB must not boot a 0-instrument
    universe that silently starves every consumer."""
    repo = _FakeInstrumentCatalogRepository([])

    with pytest.raises(RuntimeError, match="empty"):
        await SupabaseInstrumentUniverse.create(repo)


async def test_all_returns_instruments_with_no_vendor_id_leakage(
    fixture_rows: list[InstrumentRow],
) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)

    instruments = universe.all()

    assert all(isinstance(i, Instrument) for i in instruments)
    assert all(not hasattr(i, "coingecko_id") for i in instruments)
    assert all(not hasattr(i, "yfinance_symbol") for i in instruments)


async def test_by_symbol_is_case_insensitive(fixture_rows: list[InstrumentRow]) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)

    found = universe.by_symbol("btc")

    assert found is not None
    assert found.symbol == "BTC"


async def test_by_symbol_returns_none_for_unknown_symbol(fixture_rows: list[InstrumentRow]) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)

    assert universe.by_symbol("NOPE") is None


async def test_by_asset_class_filters_correctly(fixture_rows: list[InstrumentRow]) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)

    crypto = universe.by_asset_class(AssetClass.CRYPTO)

    assert len(crypto) == 5
    assert all(i.asset_class == AssetClass.CRYPTO for i in crypto)


async def test_add_then_all_includes_the_new_instrument(fixture_rows: list[InstrumentRow]) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)
    new_instrument = Instrument(
        symbol="DOGE", name="Dogecoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )

    universe.add(new_instrument)

    assert new_instrument in universe.all()
    assert len(universe.all()) == 28


async def test_add_the_same_symbol_twice_does_not_duplicate(
    fixture_rows: list[InstrumentRow],
) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)
    new_instrument = Instrument(
        symbol="DOGE", name="Dogecoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )

    universe.add(new_instrument)
    universe.add(new_instrument)

    assert len(universe.all()) == 28
    assert universe.by_symbol("DOGE") == new_instrument


async def test_all_rows_returns_raw_rows_including_vendor_ids(
    fixture_rows: list[InstrumentRow],
) -> None:
    repo = _FakeInstrumentCatalogRepository(fixture_rows)
    universe = await SupabaseInstrumentUniverse.create(repo)

    rows = universe.all_rows()

    btc_row = next(row for row in rows if row.symbol == "BTC")
    assert btc_row.coingecko_id == "bitcoin"
    eurusd_row = next(row for row in rows if row.symbol == "EURUSD")
    assert eurusd_row.yfinance_symbol == "EURUSD=X"
    assert len(rows) == 27
