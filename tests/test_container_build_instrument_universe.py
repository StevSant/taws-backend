"""`Container.build_instrument_universe()`: awaits `SupabaseInstrumentUniverse.create()`
and caches the result as the process-wide singleton `get_instrument_universe()` then
returns. This replaces the old synchronous `JsonInstrumentUniverse` construction path
(design decision #1) — `get_instrument_universe()` becomes a plain accessor over the
prebuilt singleton, never building it lazily itself.
"""

import pytest

from app.core.config import Settings
from app.core.di import Container
from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import InstrumentCatalogRepository
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse


class _FakeInstrumentCatalogRepository(InstrumentCatalogRepository):
    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows = rows

    async def upsert(self, row: InstrumentRow) -> None:
        self._rows.append(row)

    async def all_rows(self) -> list[InstrumentRow]:
        return list(self._rows)


_FIXTURE_ROWS = [
    InstrumentRow(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"),
    InstrumentRow(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="bitcoin",
    ),
]


async def test_build_instrument_universe_caches_the_prebuilt_singleton() -> None:
    container = Container(settings=Settings())
    container.get_instrument_catalog_repository = lambda: _FakeInstrumentCatalogRepository(  # type: ignore[method-assign]
        list(_FIXTURE_ROWS)
    )

    await container.build_instrument_universe()
    universe = container.get_instrument_universe()

    assert isinstance(universe, SupabaseInstrumentUniverse)
    assert len(universe.all()) == 2


async def test_get_instrument_universe_returns_the_same_instance_built() -> None:
    container = Container(settings=Settings())
    container.get_instrument_catalog_repository = lambda: _FakeInstrumentCatalogRepository(  # type: ignore[method-assign]
        list(_FIXTURE_ROWS)
    )

    await container.build_instrument_universe()
    first = container.get_instrument_universe()
    second = container.get_instrument_universe()

    assert first is second


def test_get_instrument_universe_raises_before_build() -> None:
    container = Container(settings=Settings())

    with pytest.raises(RuntimeError):
        container.get_instrument_universe()
