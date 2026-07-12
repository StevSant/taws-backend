from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.event_study_event_response import EventStudyEventResponse


class EventStudyResponse(BaseModel):
    """Response payload for `GET /api/v1/quant/event-study`."""

    model_config = ConfigDict(from_attributes=True)

    instrument_symbol: str
    lookback_days: int
    move_threshold_pct: float
    sample_size: int
    median_return_pct: float | None
    min_return_pct: float | None
    max_return_pct: float | None
    forward_1d_median_pct: float | None
    forward_7d_median_pct: float | None
    forward_30d_median_pct: float | None
    scenario_probability_pct: float | None
    scenario_probability_sample_size: int
    scenario_probability_occurrences: int
    scenario_probability_horizon_days: int | None
    scenario_probability_threshold_pct: float | None
    events: list[EventStudyEventResponse]
