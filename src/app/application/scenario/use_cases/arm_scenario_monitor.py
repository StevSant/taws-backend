import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.domain.notification.entities import ScenarioArmedNotification
from app.domain.notification.ports import NotificationChannel
from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus, ScenarioResult
from app.domain.scenario.ports import ScenarioRepository

logger = logging.getLogger(__name__)


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

    On a successful arm it delivers an immediate "you're now monitoring this" confirmation
    over the `NotificationChannel` port. Before this, arming was silent: the row was written
    and `201` returned, but the only scenario notification (`ScenarioMatchNotification`)
    fires solely if the scenario materializes — which may never happen. The confirmation is
    best-effort and never fails the arm: the port's adapters already swallow expected
    delivery failures, and this use case wraps the call besides, so a missing Telegram link
    or a transient send error can't turn a successful subscription into an error response.

    Returns `None` if `scenario_id` doesn't reference an existing `ScenarioResult` — the
    caller (the `POST /api/v1/scenarios/{id}/arm` router) turns that into a 404, same
    "use case returns `None`, router 404s" shape `GET /api/v1/scenarios/{id}` already uses.
    """

    def __init__(
        self,
        scenario_repository: ScenarioRepository,
        ttl_days: int,
        notification_channel: NotificationChannel,
        frontend_base_url: str,
    ) -> None:
        self._scenario_repository = scenario_repository
        self._ttl_days = ttl_days
        self._notification_channel = notification_channel
        self._frontend_base_url = frontend_base_url

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
        armed = await self._scenario_repository.arm_monitor(monitor)
        await self._send_armed_confirmation(armed, scenario)
        return armed

    async def _send_armed_confirmation(
        self, monitor: ScenarioMonitor, scenario: ScenarioResult
    ) -> None:
        """Best-effort confirmation. A delivery problem must never fail the arm itself, so
        this both trusts the port's never-raise contract AND guards the call."""
        notification = ScenarioArmedNotification(
            id=str(uuid.uuid4()),
            monitor_id=monitor.id,
            scenario_id=monitor.scenario_id,
            user_id=monitor.user_id,
            scenario_title=scenario.title,
            link_url=f"{self._frontend_base_url}/scenarios/{monitor.scenario_id}",
            expires_at=monitor.expires_at,
            locale=scenario.locale,
        )
        try:
            await self._notification_channel.send_scenario_armed(notification)
        except Exception:  # noqa: BLE001 — a confirmation failure must not fail the subscription.
            logger.exception(
                "Failed to send arm confirmation for monitor %s (user %s)",
                monitor.id,
                monitor.user_id,
            )
