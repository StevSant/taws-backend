"""`InstrumentRow`: the raw catalog-row DTO, including vendor-id overrides.

Unlike the pure `Instrument` entity, `InstrumentRow` carries `coingecko_id` /
`yfinance_symbol` — it's the infrastructure-facing shape of a `public.instruments`
row, consumed only by `SupabaseInstrumentUniverse` and `get_market_data_provider`'s
override-map building (never by `application/`'s core business logic).
"""

import dataclasses

import pytest

from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass


def test_round_trips_all_fields() -> None:
    row = InstrumentRow(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="bitcoin",
        yfinance_symbol=None,
    )

    assert row.symbol == "BTC"
    assert row.name == "Bitcoin"
    assert row.asset_class == AssetClass.CRYPTO
    assert row.currency == "USD"
    assert row.coingecko_id == "bitcoin"
    assert row.yfinance_symbol is None


def test_vendor_id_fields_default_to_none() -> None:
    row = InstrumentRow(
        symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
    )

    assert row.coingecko_id is None
    assert row.yfinance_symbol is None


def test_is_frozen() -> None:
    row = InstrumentRow(
        symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        row.symbol = "MSFT"  # type: ignore[misc]
