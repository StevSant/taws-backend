import asyncio
import logging

from app.application.event_intelligence.processed_event_tracker import ProcessedEventTracker
from app.application.event_intelligence.use_cases.process_incoming_event import (
    ProcessIncomingEvent,
)
from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import NewsProviderPort
from app.domain.notification.ports import NotificationChannel

logger = logging.getLogger(__name__)


class BroadcastImportantEvents:
    """Poll the news, let the LLM decide what matters, push the important ones to Telegram.

    This is the automatic replacement for the manual "send a news analysis to my Telegram"
    button (`POST /telegram/send-test-news`, which picks a RANDOM article and deliberately
    ignores importance because its only job is proving the wiring works). The pieces all
    already existed — the Gemini analyzer already returns `importance` and `should_notify`, the
    Telegram links already resolve to chat ids, APScheduler already runs five jobs — but
    nothing ever connected "a genuinely important article arrived" to "tell the user". This use
    case is that connection.

    One pass:

    1. Fetch the latest news (`NewsProviderPort` — bridged to the real Marketaux/NewsAPI/
       Finnhub/RSS/EDGAR providers by `MarketNewsEventProvider`).
    2. Drop anything already analyzed (`ProcessedEventTracker`), so an overlapping poll window
       doesn't re-bill Gemini or re-notify anyone.
    3. Analyze what's left through `ProcessIncomingEvent` (Gemini), bounded by a semaphore.
    4. Keep only events the model flagged `should_notify` AND scored at or above
       `importance_threshold`.
    5. Broadcast, newest-and-most-important first, capped at `max_alerts_per_run`.

    **Why both `should_notify` and a threshold.** `should_notify` is the model's own judgment
    and is what the product asked for; the threshold is the operator's floor underneath it. An
    LLM boolean is exactly the kind of thing that quietly drifts to "yes" after a prompt or
    model change, and the blast radius here is a push notification to every linked user — so
    the gate is config, not just vibes.

    **Why the cap.** A quiet market yields nothing; a chaotic morning can yield twenty
    "important" headlines at once. Without `max_alerts_per_run` the first genuinely busy day
    would carpet-bomb everyone's phone, which is the fastest way to get the bot muted. Events
    are sorted by importance before the cap, so what survives is the most important — not
    whatever the provider happened to list first. Anything dropped is logged rather than
    silently discarded.

    Never raises: a bad tick logs and returns what it managed, so the scheduler survives.
    """

    def __init__(
        self,
        news_provider: NewsProviderPort,
        process_incoming_event: ProcessIncomingEvent,
        notification_channel: NotificationChannel,
        processed_event_tracker: ProcessedEventTracker,
        importance_threshold: float,
        max_alerts_per_run: int,
        max_concurrency: int,
    ) -> None:
        self._news_provider = news_provider
        self._process_incoming_event = process_incoming_event
        self._notification_channel = notification_channel
        self._processed_event_tracker = processed_event_tracker
        self._importance_threshold = importance_threshold
        self._max_alerts_per_run = max_alerts_per_run
        self._max_concurrency = max_concurrency

    async def execute(self) -> list[EnrichedEvent]:
        """Run one scan pass. Returns the events actually broadcast."""
        events = await self._news_provider.fetch_latest_news()
        fresh = [event for event in events if self._processed_event_tracker.is_new(event)]
        if not fresh:
            logger.info("sentinel scan: %d event(s) fetched, none new", len(events))
            return []

        enriched = await self._analyze_all(fresh)
        important = [event for event in enriched if self._is_important(event)]
        important.sort(key=lambda event: event.importance, reverse=True)

        selected = important[: self._max_alerts_per_run]
        if len(important) > len(selected):
            # Never drop notifications silently — a capped run must look different in the logs
            # from a quiet one, or "the bot went quiet" is indistinguishable from "the bot is
            # throttling itself".
            logger.warning(
                "sentinel scan: %d event(s) cleared the importance gate but only %d were sent "
                "(SENTINEL_MAX_ALERTS_PER_RUN); dropped: %s",
                len(important),
                len(selected),
                [event.original.title for event in important[self._max_alerts_per_run :]],
            )

        for event in selected:
            await self._notification_channel.broadcast_event_alert(event)

        logger.info(
            "sentinel scan complete: %d fetched, %d new, %d analyzed, %d important, %d sent",
            len(events),
            len(fresh),
            len(enriched),
            len(important),
            len(selected),
        )
        return selected

    async def _analyze_all(self, events: list[NewsEvent]) -> list[EnrichedEvent]:
        """Analyze `events` concurrently, bounded by `_max_concurrency`.

        Marks each event processed even when its analysis FAILS. That is deliberate: a retry
        forever loop on a permanently malformed article (or a hard Gemini failure) would spend
        tokens on every tick for eternity. One shot per article; a genuinely transient blip
        costs us one missed headline, not a recurring bill.
        """
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def analyze(event: NewsEvent) -> EnrichedEvent | None:
            async with semaphore:
                try:
                    return await self._process_incoming_event.execute(event)
                except Exception:  # noqa: BLE001 — one bad article can't abort the whole scan
                    logger.exception("Failed to analyze event %r", event.title)
                    return None
                finally:
                    self._processed_event_tracker.mark_processed(event)

        results = await asyncio.gather(*(analyze(event) for event in events))
        return [event for event in results if event is not None]

    def _is_important(self, event: EnrichedEvent) -> bool:
        return event.should_notify and event.importance >= self._importance_threshold
