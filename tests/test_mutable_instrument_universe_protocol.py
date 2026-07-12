"""`MutableInstrumentUniverse`: a structural (Protocol) port for appending a newly
registered instrument to the in-memory universe index (Slice 2's `RegisterInstrument`
depends on this, never a concrete `SupabaseInstrumentUniverse`/`isinstance` check —
see design decision #7).
"""

from app.domain.market.entities import Instrument
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import MutableInstrumentUniverse


class _FakeMutableUniverse:
    """Structurally satisfies `MutableInstrumentUniverse` without inheriting it."""

    def __init__(self) -> None:
        self.added: list[Instrument] = []

    def add(self, instrument: Instrument) -> None:
        self.added.append(instrument)


def test_fake_satisfies_the_protocol_structurally() -> None:
    fake: MutableInstrumentUniverse = _FakeMutableUniverse()
    instrument = Instrument(
        symbol="DOGE", name="Dogecoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )

    fake.add(instrument)

    assert isinstance(fake, MutableInstrumentUniverse)
    assert fake.added == [instrument]  # type: ignore[attr-defined]


def test_object_without_add_does_not_satisfy_the_protocol() -> None:
    class _NotMutable:
        pass

    assert not isinstance(_NotMutable(), MutableInstrumentUniverse)
