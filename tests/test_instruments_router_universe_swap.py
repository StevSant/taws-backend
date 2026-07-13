"""Track Instruments Catalog Slice 1: `GET /api/v1/instruments` is behavior-preserving
after the `SupabaseInstrumentUniverse` DI swap.

Uses the `dependency_overrides` pattern from `test_quant_stats_candles.py`: builds a
`SupabaseInstrumentUniverse` from a 27-row fake `InstrumentCatalogRepository` (the
same rows `universe.json` carried pre-swap) and asserts the router's response is
identical in count/symbol/name/asset_class/currency to what `JsonInstrumentUniverse`
used to return — no production code path is touched by this test beyond DI wiring.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_instrument_universe
from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse
from app.main import create_app

_SEED_PATH = Path(__file__).resolve().parent.parent / "src/app/infrastructure/seeds/universe.json"


def _seed_rows() -> list[InstrumentRow]:
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


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    universe = SupabaseInstrumentUniverse(_seed_rows())

    app.dependency_overrides[get_instrument_universe] = lambda: universe
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_list_instruments_returns_the_same_27_rows_as_the_json_universe(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/instruments")

    assert response.status_code == 200
    body = response.json()

    assert len(body) == 27

    expected_by_symbol = {row.symbol: row for row in _seed_rows()}
    for item in body:
        expected = expected_by_symbol[item["symbol"]]
        assert item["name"] == expected.name
        assert item["asset_class"] == expected.asset_class.value
        assert item["currency"] == expected.currency
        assert "coingecko_id" not in item
        assert "yfinance_symbol" not in item


def test_list_instruments_filters_by_asset_class(client: TestClient) -> None:
    response = client.get("/api/v1/instruments?asset_class=crypto")

    assert response.status_code == 200
    body = response.json()

    assert len(body) == 5
    assert all(item["asset_class"] == "crypto" for item in body)
