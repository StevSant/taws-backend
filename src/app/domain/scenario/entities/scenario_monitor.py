from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.scenario.entities.scenario_monitor_status import ScenarioMonitorStatus


@dataclass(slots=True)
class ScenarioMonitor:
    """An "armed" Watchdog rule for one saved `ScenarioResult` (issue #18) — "Simulate ->
    monitor -> get pinged."

    Created by `ArmScenarioMonitor` (`application/scenario/use_cases/
    arm_scenario_monitor.py`) when a user arms a scenario they've generated, and evaluated
    by `EvaluateScenarioMonitors` (`application/watchdog/use_cases/
    evaluate_scenario_monitors.py`) on Watchdog's scheduled pass — see that use case's
    docstring for the exact matching rules.

    Keyed by `user_id`, NOT `watchlist_id`: unlike `Alert`/`BriefingReadyNotification`
    (both watchlist-scoped features), arming a scenario has nothing to do with whether the
    user happens to have a watchlist containing the scenario's affected symbols — it's a
    direct "notify me" action by one user on one scenario. Telegram delivery resolves
    straight from `user_id` via `TelegramLinkRepository.get_by_user_id`, skipping the
    watchlist hop entirely (see `ScenarioMatchNotification`'s docstring).

    One monitor per `(scenario_id, user_id)` pair (enforced by a unique constraint in
    migration `0008_scenario_monitors.py`): re-arming an existing monitor resets it back to
    `ARMED` with a fresh `armed_at`/`expires_at` window rather than creating a duplicate row
    (see `ArmScenarioMonitor`).

    On a match, the monitor transitions to `MATCHED` and stays there — it does NOT
    auto-disarm (i.e. get deleted). Rationale: disarming is destructive (loses the match
    record), and a "materializing" call is exactly the kind of thing a user should be able
    to look back on later (e.g. from a future monitors list view); `EvaluateScenarioMonitors`
    simply stops re-evaluating anything not in `ARMED` status, so a matched monitor never
    re-fires a second alert. A user who wants to watch the same scenario again can re-arm
    it explicitly.

    No trading/execution fields exist — same compliance invariant as every other entity in
    this codebase; a match is informational only.
    """

    id: str
    scenario_id: str
    user_id: str
    status: ScenarioMonitorStatus
    armed_at: datetime
    expires_at: datetime
    matched_at: datetime | None = None
    match_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
