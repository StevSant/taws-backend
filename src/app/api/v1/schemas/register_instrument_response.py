from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.instrument_response import InstrumentResponse


class RegisterInstrumentResponse(BaseModel):
    """Response payload for `POST /api/v1/instruments`.

    `watchlisted` is `False` only on the 502 partial-failure outcome (catalog
    upsert succeeded, subsequent watchlist add failed) — the instrument is
    still real and persisted either way.
    """

    model_config = ConfigDict(from_attributes=True)

    instrument: InstrumentResponse
    watchlisted: bool
