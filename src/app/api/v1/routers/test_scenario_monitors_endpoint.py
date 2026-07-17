"""Endpoint test for `GET /api/v1/scenarios/monitors` (issue #18 / C3).

The in-app notification poller diffs this authenticated read to raise an `ARMED`->`MATCHED`
breach in the bell, so it depends on two contracts this test pins by driving the real route
through `TestClient` with DI overrides:

- the caller's monitors come back with their live `status` and the originating scenario's
  `title` (resolved via `ScenarioRepository.get`), plus `match_reason`/`matched_at` on a
  matched row;
- an `armed` (not-yet-matched) row carries `null` `matched_at`/`match_reason` — the poller
  relies on that to tell "still armed" from "just matched".

Auth is exercised implicitly: the route declares `require_current_user`, and the override
here is what supplies the caller whose id `list_monitors_for_user` is scoped to. Per
`backend/CLAUDE.md`: a minimal targeted test next to the behavior under test, not the start
of a broad suite.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_scenario_repository, require_current_user
from app.api.v1.schemas import CurrentUser
from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities import (
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioMonitor,
    ScenarioMonitorStatus,
    ScenarioResult,
    ScenarioSpec,
)
from app.domain.scenario.ports import ScenarioRepository
from app.main import app

_USER_ID = "dev-user"
_MATCHED_SCENARIO_ID = "scenario-matched"
_ARMED_SCENARIO_ID = "scenario-armed"
_MATCH_REASON = "AAPL moved +6.20% since the monitor was armed — crosses the medium threshold."


def _scenario(scenario_id: str, title: str) -> ScenarioResult:
    return ScenarioResult(
        id=scenario_id,
        spec=ScenarioSpec(
            entity="AAPL",
            event_type="shock",
            magnitude=ScenarioMagnitude.MEDIUM,
            horizon=ScenarioHorizon.SHORT_TERM,
            title=title,
            description="normalized restatement",
        ),
        title=title,
        narrative="narrative",
        impact_map=[],
        consequence_chain=ConsequenceChain(
            id="chain", subject="s", nodes=[], edges=[], disclaimer="research"
        ),
        recommended_actions=[],
        disclaimer="research",
    )


def _monitor(scenario_id: str, status: ScenarioMonitorStatus) -> ScenarioMonitor:
    now = datetime.now(UTC)
    is_matched = status == ScenarioMonitorStatus.MATCHED
    return ScenarioMonitor(
        id=f"monitor-{scenario_id}",
        scenario_id=scenario_id,
        user_id=_USER_ID,
        status=status,
        armed_at=now - timedelta(days=3),
        expires_at=now + timedelta(days=4),
        matched_at=now if is_matched else None,
        match_reason=_MATCH_REASON if is_matched else None,
    )


class _StubScenarioRepository(ScenarioRepository):
    """Only `list_monitors_for_user` + `get` are exercised by the monitors read."""

    def __init__(
        self, monitors: list[ScenarioMonitor], scenarios: dict[str, ScenarioResult]
    ) -> None:
        self._monitors = monitors
        self._scenarios = scenarios

    async def get(self, scenario_id: str) -> ScenarioResult | None:
        return self._scenarios.get(scenario_id)

    async def list_monitors_for_user(self, user_id: str) -> list[ScenarioMonitor]:
        return [monitor for monitor in self._monitors if monitor.user_id == user_id]

    async def create(self, result: ScenarioResult) -> ScenarioResult:
        raise NotImplementedError

    async def list_recent(self, user_id: str, limit: int = 20) -> list[ScenarioResult]:
        raise NotImplementedError

    async def get_latest_for_preset(self, preset_id: str, locale: str) -> ScenarioResult | None:
        raise NotImplementedError

    async def prune_for_preset(self, preset_id: str, locale: str, keep: int) -> int:
        raise NotImplementedError

    async def arm_monitor(self, monitor: ScenarioMonitor) -> ScenarioMonitor:
        raise NotImplementedError

    async def get_monitor_for_user(self, scenario_id: str, user_id: str) -> ScenarioMonitor | None:
        raise NotImplementedError

    async def list_armed_monitors(self) -> list[ScenarioMonitor]:
        raise NotImplementedError

    async def mark_monitor_matched(self, monitor_id: str, match_reason: str) -> ScenarioMonitor:
        raise NotImplementedError

    async def mark_monitor_expired(self, monitor_id: str) -> ScenarioMonitor:
        raise NotImplementedError

    async def disarm_monitor(self, scenario_id: str, user_id: str) -> None:
        raise NotImplementedError


def _override_dependencies() -> None:
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )
    monitors = [
        _monitor(_MATCHED_SCENARIO_ID, ScenarioMonitorStatus.MATCHED),
        _monitor(_ARMED_SCENARIO_ID, ScenarioMonitorStatus.ARMED),
    ]
    scenarios = {
        _MATCHED_SCENARIO_ID: _scenario(_MATCHED_SCENARIO_ID, "Fed hikes 50bp"),
        _ARMED_SCENARIO_ID: _scenario(_ARMED_SCENARIO_ID, "Oil spikes to $120"),
    }
    app.dependency_overrides[get_scenario_repository] = lambda: _StubScenarioRepository(
        monitors, scenarios
    )


def test_list_scenario_monitors_returns_status_and_scenario_title() -> None:
    _override_dependencies()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/scenarios/monitors")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2

    matched = next(row for row in body if row["scenario_id"] == _MATCHED_SCENARIO_ID)
    assert matched["title"] == "Fed hikes 50bp"
    assert matched["status"] == ScenarioMonitorStatus.MATCHED.value
    assert matched["match_reason"] == _MATCH_REASON
    assert matched["matched_at"] is not None
    assert matched["armed_at"] is not None

    armed = next(row for row in body if row["scenario_id"] == _ARMED_SCENARIO_ID)
    assert armed["title"] == "Oil spikes to $120"
    assert armed["status"] == ScenarioMonitorStatus.ARMED.value
    # The poller tells "still armed" from "just matched" by these two staying null.
    assert armed["match_reason"] is None
    assert armed["matched_at"] is None
