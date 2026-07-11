from pydantic import BaseModel, ConfigDict

from app.domain.market.entities import AssetClass


class InstrumentResponse(BaseModel):
    """Response payload for a single instrument in `GET /api/v1/instruments`."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
