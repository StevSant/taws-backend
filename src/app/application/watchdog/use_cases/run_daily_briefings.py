import uuid

from app.application.briefing import EmptyWatchlistError
from app.application.briefing.use_cases import GenerateBriefing
from app.domain.briefing.entities import Briefing
from app.domain.notification.entities import BriefingReadyNotification
from app.domain.notification.ports import NotificationChannel
from app.domain.watchlist.ports import WatchlistRepository

# Truncates a persisted briefing's executive summary down to a Telegram-message-friendly
# headline — the full document is always one tap away via `link_url`, so the notification
# itself only needs to be a short teaser, not a duplicate of the whole summary.
_HEADLINE_MAX_CHARS = 240


class RunDailyBriefings:
    """Daily scheduled briefing run (issue #10, acceptance criterion 4): regenerates an
    Advisor briefing for every active watchlist, landing each in the review queue.

    "Landing in the review queue" interpretation: briefings are already persisted via
    `BriefingRepository.create` (inside `GenerateBriefing.execute`) and already reviewable
    through the existing `GET /api/v1/watchlists/{id}/briefings` + review endpoints (issue #4,
    already on `main`) — there is no separate queue data structure to build here; persistence
    already IS the queue. This reuses the EXISTING `GenerateBriefing` use case (issue #3)
    rather than reimplementing briefing composition, so both paths share one source of truth.

    Telegram notification on completion (issue #16): after each watchlist's briefing is
    generated and persisted, hands a composed `BriefingReadyNotification` to the
    `NotificationChannel` port — the SAME port `RunWatchdogScan` (issue #10) already uses
    for signal alerts, now with `TelegramNotificationChannel` (issue #14) as a real
    adapter. Deliberately only wired here, not inside `GenerateBriefing` itself: the
    on-demand path (`POST /api/v1/watchlists/{id}/briefings`) is a button the user just
    pressed while looking at the app, so notifying them via Telegram about output they
    triggered themselves would be redundant/spammy — the acceptance criterion is explicit
    that this fires "on scheduled briefing completion". A delivery failure (no linked
    chat, a transient Telegram error) never fails the run — `NotificationChannel.send_
    briefing_ready` has the same "never raises" contract `send` does, so one watchlist's
    notification failure can't take down the rest of the batch.

    Global (not user-scoped), like `RunWatchdogScan` — see that class's docstring for why.
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        generate_briefing: GenerateBriefing,
        notification_channel: NotificationChannel,
        frontend_base_url: str,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._generate_briefing = generate_briefing
        self._notification_channel = notification_channel
        self._frontend_base_url = frontend_base_url

    async def execute(self, locale: str) -> list[Briefing]:
        watchlists = await self._watchlist_repository.list_all()
        briefings: list[Briefing] = []
        for watchlist in watchlists:
            try:
                briefing = await self._generate_briefing.execute(watchlist.id, locale=locale)
            except EmptyWatchlistError:
                continue  # nothing tracked yet — nothing to brief, not a failure
            briefings.append(briefing)
            await self._notification_channel.send_briefing_ready(
                _compose_notification(briefing, self._frontend_base_url)
            )
        return briefings


def _compose_notification(briefing: Briefing, frontend_base_url: str) -> BriefingReadyNotification:
    headline = briefing.summary[:_HEADLINE_MAX_CHARS]
    if len(briefing.summary) > _HEADLINE_MAX_CHARS:
        headline = headline.rstrip() + "..."
    return BriefingReadyNotification(
        id=str(uuid.uuid4()),
        briefing_id=briefing.id,
        watchlist_id=briefing.watchlist_id,
        headline=headline,
        link_url=(
            f"{frontend_base_url.rstrip('/')}/watchlists/{briefing.watchlist_id}"
            f"?briefing={briefing.id}"
        ),
    )
