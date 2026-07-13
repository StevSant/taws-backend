"""`RegisterInstrumentRequest`/`RegisterInstrumentResponse`: request/response
schemas for `POST /api/v1/instruments`.
"""

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    InstrumentResponse,
    RegisterInstrumentRequest,
    RegisterInstrumentResponse,
)
from app.domain.market.entities import AssetClass, Instrument


def test_register_instrument_request_validates_required_fields() -> None:
    request = RegisterInstrumentRequest(coingecko_id="dogecoin", symbol="doge", name="Dogecoin")

    assert request.coingecko_id == "dogecoin"
    assert request.symbol == "doge"
    assert request.name == "Dogecoin"


@pytest.mark.parametrize(
    "bad_symbol",
    [
        "",
        "a" * 21,
        "DOGE/USD",
        "DOGE USD",
        "<script>",
    ],
)
def test_register_instrument_request_rejects_malformed_symbol(bad_symbol: str) -> None:
    """MEDIUM fix (post-hoc adversarial review): ANY authenticated user can
    trigger this service-role (RLS-bypassing) global-catalog write, so the
    request schema must bound `symbol` to a sane character set/length instead
    of accepting arbitrary junk."""
    with pytest.raises(ValidationError):
        RegisterInstrumentRequest(coingecko_id="dogecoin", symbol=bad_symbol, name="Dogecoin")


@pytest.mark.parametrize(
    "bad_coingecko_id",
    [
        "",
        "a" * 81,
        "Dogecoin!",
        "doge coin",
        "<script>alert(1)</script>",
    ],
)
def test_register_instrument_request_rejects_malformed_coingecko_id(bad_coingecko_id: str) -> None:
    with pytest.raises(ValidationError):
        RegisterInstrumentRequest(coingecko_id=bad_coingecko_id, symbol="doge", name="Dogecoin")


def test_register_instrument_request_accepts_valid_symbols_with_dots_and_dashes() -> None:
    """Some real vendor symbols legitimately contain `.`/`-` (e.g. share classes)."""
    request = RegisterInstrumentRequest(coingecko_id="berkshire-hathaway", symbol="BRK.A", name="X")

    assert request.symbol == "BRK.A"


def test_register_instrument_request_rejects_name_over_max_length() -> None:
    with pytest.raises(ValidationError):
        RegisterInstrumentRequest(coingecko_id="dogecoin", symbol="doge", name="x" * 201)


def test_register_instrument_response_serializes_instrument_and_watchlisted_flag() -> None:
    instrument = Instrument(
        symbol="DOGE", name="Dogecoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )
    response = RegisterInstrumentResponse(
        instrument=InstrumentResponse.model_validate(instrument), watchlisted=True
    )

    dumped = response.model_dump()
    assert dumped["instrument"]["symbol"] == "DOGE"
    assert dumped["watchlisted"] is True
