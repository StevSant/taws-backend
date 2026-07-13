"""Track Instruments Catalog Slice 3 (enrichment): `EnrichedInstrument` new fields.

`EnrichedInstrument` gains `market_cap`, `volume_24h`, `change_7d_pct` (additive,
default `None`) — the existing 10 fields keep their exact name/type
(instrument-enrichment spec's "backward compatible" requirement).
"""

from app.application.instruments.enriched_instrument import EnrichedInstrument
from app.domain.market.entities import AssetClass


def _build(**overrides: object) -> EnrichedInstrument:
    defaults: dict[str, object] = dict(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        last_price=50_000.0,
        price_delta_pct=1.5,
        volatility_pct=2.5,
        volatility_regime=None,
        sparkline=[1.0, 2.0],
        latest_signal=None,
    )
    defaults.update(overrides)
    return EnrichedInstrument(**defaults)  # type: ignore[arg-type]


def test_existing_ten_fields_are_unchanged() -> None:
    row = _build()

    assert row.symbol == "BTC"
    assert row.name == "Bitcoin"
    assert row.asset_class == AssetClass.CRYPTO
    assert row.currency == "USD"
    assert row.last_price == 50_000.0
    assert row.price_delta_pct == 1.5
    assert row.volatility_pct == 2.5
    assert row.volatility_regime is None
    assert row.sparkline == [1.0, 2.0]
    assert row.latest_signal is None


def test_new_fields_default_to_none() -> None:
    row = _build()

    assert row.market_cap is None
    assert row.volume_24h is None
    assert row.change_7d_pct is None


def test_new_fields_can_be_set() -> None:
    row = _build(market_cap=1_000.0, volume_24h=500.0, change_7d_pct=-4.2)

    assert row.market_cap == 1_000.0
    assert row.volume_24h == 500.0
    assert row.change_7d_pct == -4.2
