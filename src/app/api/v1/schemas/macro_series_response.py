from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.macro_observation_response import MacroObservationResponse
from app.domain.market.entities import MacroIndicator


class MacroSeriesResponse(BaseModel):
    """Response payload for `GET /api/v1/macro/series/{indicator}`: an indicator's history.

    `observations` is ordered oldest -> newest (sparkline-ready); `latest` is the most recent
    reading, or `None` when the series came back empty.
    """

    model_config = ConfigDict(from_attributes=True)

    indicator: MacroIndicator
    series_id: str
    observations: list[MacroObservationResponse]
    latest: MacroObservationResponse | None
