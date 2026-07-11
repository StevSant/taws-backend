from app.application.briefing import EmptyWatchlistError
from app.application.briefing.use_cases import GenerateBriefing
from app.domain.briefing.entities import Briefing
from app.domain.watchlist.ports import WatchlistRepository


class RunDailyBriefings:
    """Daily scheduled briefing run (issue #10, acceptance criterion 4): regenerates an
    Advisor briefing for every active watchlist, landing each in the review queue.

    "Landing in the review queue" interpretation: briefings are already persisted via
    `BriefingRepository.create` (inside `GenerateBriefing.execute`) and already reviewable
    through the existing `GET /api/v1/watchlists/{id}/briefings` + review endpoints (issue #4,
    already on `main`) — there is no separate queue data structure to build here; persistence
    already IS the queue. This reuses the EXISTING `GenerateBriefing` use case (issue #3)
    rather than reimplementing briefing composition, so both paths share one source of truth.

    Global (not user-scoped), like `RunWatchdogScan` — see that class's docstring for why.
    """

    def __init__(
        self, watchlist_repository: WatchlistRepository, generate_briefing: GenerateBriefing
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._generate_briefing = generate_briefing

    async def execute(self) -> list[Briefing]:
        watchlists = await self._watchlist_repository.list_all()
        briefings: list[Briefing] = []
        for watchlist in watchlists:
            try:
                briefings.append(await self._generate_briefing.execute(watchlist.id))
            except EmptyWatchlistError:
                continue  # nothing tracked yet — nothing to brief, not a failure
        return briefings
