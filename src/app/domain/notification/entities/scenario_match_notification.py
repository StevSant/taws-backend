from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class ScenarioMatchNotification:
    """A Watchdog-composed notification that an armed `ScenarioMonitor`'s scenario appears
    to be materializing (issue #18) — a matching signal or a large-enough price move was
    detected on one of the scenario's affected symbols since it was armed. See
    `EvaluateScenarioMonitors` (`application/watchdog/use_cases/
    evaluate_scenario_monitors.py`) for the exact matching rules that produce `match_reason`.

    Produced by `EvaluateScenarioMonitors` and handed to a `NotificationChannel` port
    adapter for delivery — same "compose -> hand to port -> adapter resolves recipient ->
    delivers" pattern `Alert`/`BriefingReadyNotification` use.

    Kept as its own entity rather than reusing `Alert`: `Alert.signal_id`/
    `Alert.instrument_symbol` are both required, single-value fields tied to one `Signal`,
    but a scenario match isn't about any single signal — it's "this scenario, watched by
    this user, now looks like it's happening" (see #16's precedent for the same "shape
    doesn't fit `Alert`" reasoning behind `BriefingReadyNotification`).

    Keyed by `user_id`, NOT `watchlist_id`: unlike `Alert`/`BriefingReadyNotification`,
    there's no watchlist in the loop here at all — `ScenarioMonitor.user_id` is the
    direct recipient. Delivery resolves `user_id` -> `TelegramLinkRepository.
    get_by_user_id` -> `chat_id` directly, skipping the `watchlist_id` ->
    `WatchlistRepository.get` -> owning `user_id` hop `TelegramNotificationChannel` needs
    for the other two notification kinds.
    """

    id: str
    monitor_id: str
    scenario_id: str
    user_id: str
    scenario_title: str
    match_reason: str
    link_url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
