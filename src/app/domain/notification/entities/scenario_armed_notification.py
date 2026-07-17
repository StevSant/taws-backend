from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class ScenarioArmedNotification:
    """A confirmation delivered the moment a user arms a `ScenarioMonitor` (issue #18) —
    "you're now watching this scenario, and here's when the watch lapses".

    This exists because arming was silent: `POST /scenarios/{id}/arm` wrote a row and
    returned `201`, but nothing ever told the user the subscription took, and the only other
    scenario notification (`ScenarioMatchNotification`) fires only if the scenario actually
    materializes — which may never happen, and certainly not during a demo. An immediate
    confirmation makes "Monitorear escenario" tangibly do something.

    Same shape and delivery path as `ScenarioMatchNotification`: keyed by `user_id` (the
    arming user is the direct recipient, resolved straight to a Telegram `chat_id` with no
    watchlist hop), composed by the `ArmScenarioMonitor` use case, and handed to a
    `NotificationChannel` adapter. `locale` is carried so the confirmation is written in the
    same language as the scenario itself (`ScenarioResult.locale`); `expires_at` mirrors the
    monitor's TTL window so the message can say when the watch ends.
    """

    id: str
    monitor_id: str
    scenario_id: str
    user_id: str
    scenario_title: str
    link_url: str
    expires_at: datetime
    locale: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
