import uuid
from datetime import UTC, datetime, timedelta

from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus
from app.domain.scenario.ports import ScenarioRepository


class ArmScenarioMonitor:
    """Arm-monitor action on a saved `ScenarioResult` (issue #18): the entry point into
    the "Simulate -> monitor -> get pinged" story. Turns a scenario the user has already
    generated into a standing Watchdog rule for THEM specifically (see `ScenarioMonitor`'s
    docstring for why this is `user_id`-keyed, not `watchlist_id`-keyed).

    Idempotent per `(scenario_id, user_id)`: if this user already has a monitor for this
    scenario (in any status — `ARMED`, `MATCHED`, or `EXPIRED`), re-arming reuses that same
    row's id and resets it back to `ARMED` with a fresh `armed_at`/`expires_at` window and a
    cleared match, rather than creating a duplicate. This makes "re-arm a matched or expired
    scenario" the natural, obvious way to watch it again — no separate "reset" action needed.

    Returns `None` if `scenario_id` doesn't reference an existing `ScenarioResult` — the
    caller (the `POST /api/v1/scenarios/{id}/arm` router) turns that into a 404, same
    "use case returns `None`, router 404s" shape `GET /api/v1/scenarios/{id}` already uses.
    """

    def __init__(self, scenario_repository: ScenarioRepository, ttl_days: int) -> None:
        self._scenario_repository = scenario_repository
        self._ttl_days = ttl_days

    async def execute(self, scenario_id: str, user_id: str) -> ScenarioMonitor | None:
        scenario = await self._scenario_repository.get(scenario_id)
        if scenario is None:
            return None

        existing = await self._scenario_repository.get_monitor_for_user(scenario_id, user_id)
        now = datetime.now(UTC)
        monitor = ScenarioMonitor(
            id=existing.id if existing is not None else str(uuid.uuid4()),
            scenario_id=scenario_id,
            user_id=user_id,
            status=ScenarioMonitorStatus.ARMED,
            armed_at=now,
            expires_at=now + timedelta(days=self._ttl_days),
            matched_at=None,
            match_reason=None,
        )
        return await self._scenario_repository.arm_monitor(monitor)
