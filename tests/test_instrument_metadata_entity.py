"""Track Instruments Catalog Slice 3 (enrichment): `InstrumentMetadata` entity.

Frozen DTO carrying the three new CoinGecko `/coins/markets`-sourced fields
(`market_cap`, `volume_24h`, `change_7d_pct`), all nullable so a partial or
absent CoinGecko response degrades gracefully instead of crashing.
"""

from app.domain.market.entities import InstrumentMetadata


def test_instrument_metadata_round_trips_all_fields() -> None:
    metadata = InstrumentMetadata(
        market_cap=1_234_567.89, volume_24h=98_765.43, change_7d_pct=-3.21
    )

    assert metadata.market_cap == 1_234_567.89
    assert metadata.volume_24h == 98_765.43
    assert metadata.change_7d_pct == -3.21


def test_instrument_metadata_fields_are_nullable() -> None:
    metadata = InstrumentMetadata(market_cap=None, volume_24h=None, change_7d_pct=None)

    assert metadata.market_cap is None
    assert metadata.volume_24h is None
    assert metadata.change_7d_pct is None


def test_instrument_metadata_is_frozen() -> None:
    metadata = InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0)

    try:
        metadata.market_cap = 999.0  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("InstrumentMetadata must be immutable (frozen dataclass)")
