"""`MutableInstrumentUniverse`: a structural (Protocol) port for appending a newly
registered instrument to the in-memory universe index (Slice 2's `RegisterInstrument`
depends on this, never a concrete `SupabaseInstrumentUniverse`/`isinstance` check —
see design decision #7).
"""

from app.domain.market.entities import Instrument, InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import MutableInstrumentUniverse


class _FakeMutableUniverse:
    """Structurally satisfies `MutableInstrumentUniverse` without inheriting it."""

    def __init__(self) -> None:
        self.added: list[Instrument] = []
        self.added_rows: list[InstrumentRow] = []

    def add(self, instrument: Instrument) -> None:
        self.added.append(instrument)

    def add_row(self, row: InstrumentRow) -> None:
        self.added_rows.append(row)


def test_fake_satisfies_the_protocol_structurally() -> None:
    fake: MutableInstrumentUniverse = _FakeMutableUniverse()
    instrument = Instrument(
        symbol="DOGE", name="Dogecoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )
    row = InstrumentRow(
        symbol="DOGE",
        name="Dogecoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="dogecoin",
    )

    fake.add(instrument)
    fake.add_row(row)

    assert isinstance(fake, MutableInstrumentUniverse)
    assert fake.added == [instrument]  # type: ignore[attr-defined]
    assert fake.added_rows == [row]  # type: ignore[attr-defined]


def test_object_without_add_does_not_satisfy_the_protocol() -> None:
    class _NotMutable:
        pass

    assert not isinstance(_NotMutable(), MutableInstrumentUniverse)
