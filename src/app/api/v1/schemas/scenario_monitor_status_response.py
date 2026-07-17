from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.scenario.entities import ScenarioMonitorStatus


class ScenarioMonitorStatusResponse(BaseModel):
    """One row of the caller's armed Scenario Monitors with its live status (issue #18 / C3).

    Backs `GET /api/v1/scenarios/monitors`, which the frontend's in-app notification poller
    diffs to raise an `ARMED`->`MATCHED` breach in the bell (Telegram delivery already fires
    server-side). Deliberately leaner than `ScenarioMonitorResponse` — no
    `id`/`user_id`/`expires_at`/`created_at`, which the poller doesn't need — and enriched with
    the originating scenario's `title` so the notification copy is a single call, not a fan-out.
    """

    model_config = ConfigDict(from_attributes=True)

    scenario_id: str
    title: str
    status: ScenarioMonitorStatus
    armed_at: datetime
    matched_at: datetime | None = None
    match_reason: str | None = None
