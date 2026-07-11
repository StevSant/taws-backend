from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.scenario.entities import ScenarioMonitorStatus


class ScenarioMonitorResponse(BaseModel):
    """Response payload for an armed `ScenarioMonitor` (issue #18)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    scenario_id: str
    user_id: str
    status: ScenarioMonitorStatus
    armed_at: datetime
    expires_at: datetime
    matched_at: datetime | None
    match_reason: str | None
    created_at: datetime
