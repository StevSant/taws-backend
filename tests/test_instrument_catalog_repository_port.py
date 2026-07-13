"""`InstrumentCatalogRepository` port: the ABC any catalog persistence adapter
implements. Verified with a minimal fake, matching how every other port's ABC
contract is exercised in this codebase (fakes over mocks for structural checks).
"""

import pytest

from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import InstrumentCatalogRepository


class _FakeInstrumentCatalogRepository(InstrumentCatalogRepository):
    def __init__(self) -> None:
        self.rows: list[InstrumentRow] = []

    async def upsert(self, row: InstrumentRow) -> None:
        self.rows.append(row)

    async def all_rows(self) -> list[InstrumentRow]:
        return list(self.rows)


def test_cannot_instantiate_the_abstract_port_directly() -> None:
    with pytest.raises(TypeError):
        InstrumentCatalogRepository()  # type: ignore[abstract]


async def test_fake_implementation_satisfies_the_contract() -> None:
    repo = _FakeInstrumentCatalogRepository()
    row = InstrumentRow(symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")

    await repo.upsert(row)
    rows = await repo.all_rows()

    assert rows == [row]
