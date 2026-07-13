"""Track Instruments Catalog Slice 3 (enrichment): `InstrumentMetadataProvider` port.

ABC declares `async get_metadata_batch(symbols) -> dict[str, InstrumentMetadata]` —
ONE batch call per invocation (design decision #2), never one call per symbol.
"""

from app.domain.market.entities import InstrumentMetadata
from app.domain.market.ports import InstrumentMetadataProvider


class _FakeInstrumentMetadataProvider(InstrumentMetadataProvider):
    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        return {
            symbol: InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0)
            for symbol in symbols
        }


async def test_fake_provider_satisfies_the_abc() -> None:
    provider = _FakeInstrumentMetadataProvider()

    result = await provider.get_metadata_batch(["BTC", "ETH"])

    assert set(result.keys()) == {"BTC", "ETH"}
    assert result["BTC"] == InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0)


def test_port_is_abstract_and_cannot_be_instantiated_directly() -> None:
    try:
        InstrumentMetadataProvider()  # type: ignore[abstract]
    except TypeError:
        return
    raise AssertionError("InstrumentMetadataProvider must be an ABC (not directly instantiable)")
