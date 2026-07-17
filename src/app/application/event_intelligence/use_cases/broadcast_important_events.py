import asyncio
import logging
from collections.abc import Iterable, Sequence

from app.application.event_intelligence.build_event_relevance_vocabulary import (
    build_event_relevance_vocabulary,
)
from app.application.event_intelligence.is_event_relevant import is_event_relevant
from app.application.event_intelligence.normalize_affected_assets import normalize_affected_assets
from app.application.event_intelligence.processed_event_tracker import ProcessedEventTracker
from app.application.event_intelligence.use_cases.process_incoming_event import (
    ProcessIncomingEvent,
)
from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import EventAnalyzerPort, NewsProviderPort
from app.domain.market.ports import InstrumentUniverse
from app.domain.notification.ports import NotificationChannel
from app.domain.watchlist.ports import WatchlistRepository

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
    3. RELEVANCE PRE-GATE (cheap, no AI): drop any article whose raw title+description mentions
       neither a watchlisted symbol/company name (the union of all users' watchlists, resolved to
       canonical names via the instrument universe) NOR a configured macro keyword (Fed, inflation,
       CPI, ...). The match vocabulary is built ONCE per scan (`build_event_relevance_vocabulary`)
       and each survivor decided by `is_event_relevant` (whole-word, case-insensitive). This is the
       token-saver: Gemini never sees an obviously off-topic headline. It degrades OPEN — any
       failure building the vocabulary falls back to analyzing everything, so the pre-gate can
       never be the thing that silences the scan.
    4. Analyze what's left through `ProcessIncomingEvent` (Gemini), bounded by a semaphore.
    5. Keep only events the model flagged `should_notify` AND scored at or above
       `importance_threshold`.
    6. ROUTE each surviving event, newest-and-most-important first, capped at
       `max_alerts_per_run` (see `_route` for the hybrid broadcast-vs-watchlist split).

    **Hybrid delivery (broadcast vs watchlist-targeted).** Clearing the step-4 gate only means
    "important enough to interrupt someone" — not necessarily "important enough to interrupt
    EVERYONE". So a second, higher floor (`broadcast_importance_threshold`) decides *who*:

    - At or above the floor -> a genuinely market-moving event -> `broadcast_event_alert` to
      every linked chat (the original behavior, unchanged).
    - Below the floor -> a merely notable event -> delivered only to users whose watchlist
      contains one of its affected assets (`send_event_alert_to_user` per matched user). No
      affected assets, or no user tracking them, means it goes to nobody — better a missed niche
      alert than carpet-bombing everyone with a mid-tier headline about one instrument.

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
        watchlist_repository: WatchlistRepository,
        instrument_universe: InstrumentUniverse,
        event_analyzer: EventAnalyzerPort,
        importance_threshold: float,
        broadcast_importance_threshold: float,
        max_alerts_per_run: int,
        max_concurrency: int,
        macro_keywords: Sequence[str],
        min_symbol_match_length: int,
    ) -> None:
        self._news_provider = news_provider
        self._process_incoming_event = process_incoming_event
        self._notification_channel = notification_channel
        self._processed_event_tracker = processed_event_tracker
        self._watchlist_repository = watchlist_repository
        self._instrument_universe = instrument_universe
        self._event_analyzer = event_analyzer
        self._importance_threshold = importance_threshold
        self._broadcast_importance_threshold = broadcast_importance_threshold
        self._max_alerts_per_run = max_alerts_per_run
        self._max_concurrency = max_concurrency
        self._macro_keywords = macro_keywords
        self._min_symbol_match_length = min_symbol_match_length

    async def execute(self) -> list[EnrichedEvent]:
        """Run one scan pass. Returns the events actually broadcast."""
        events = await self._news_provider.fetch_latest_news()
        fresh = [event for event in events if self._processed_event_tracker.is_new(event)]
        if not fresh:
            logger.info("sentinel scan: %d event(s) fetched, none new", len(events))
            return []

        relevant = await self._filter_relevant(fresh)
        if not relevant:
            logger.info(
                "sentinel scan: %d new event(s), none passed the relevance pre-gate", len(fresh)
            )
            return []

        enriched = await self._analyze_all(relevant)
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
            await self._route(event)

        logger.info(
            "sentinel scan complete: %d fetched, %d new, %d relevant, %d analyzed, "
            "%d important, %d routed",
            len(events),
            len(fresh),
            len(relevant),
            len(enriched),
            len(important),
            len(selected),
        )
        return selected

    async def _filter_relevant(self, events: list[NewsEvent]) -> list[NewsEvent]:
        """Cheap, no-AI relevance pre-gate applied BEFORE Gemini (see class docstring, step 3).

        Builds the two-track match vocabulary ONCE (one `list_all_tracked_symbols` read + the
        universe's canonical names + the configured macro keywords), then keeps only articles whose
        raw title or description hits a tracked symbol/company name or a macro keyword. Every drop
        is a Gemini call not spent.

        Degrades OPEN: any failure loading the watchlist union falls back to analyzing all, and an
        empty vocabulary (no macro keywords AND no tracked symbols) is treated as "gate disabled",
        so the pre-gate can never be the thing that silences the scan. Drops are logged, never
        silent.
        """
        try:
            tracked_symbols = await self._watchlist_repository.list_all_tracked_symbols()
        except Exception:  # noqa: BLE001 — a failed watchlist read must not abort the scan
            logger.exception(
                "sentinel relevance pre-gate: could not load tracked symbols; analyzing all"
            )
            return events

        vocabulary = build_event_relevance_vocabulary(
            tracked_symbols,
            self._instrument_universe,
            self._macro_keywords,
            self._min_symbol_match_length,
        )
        if vocabulary.is_empty:
            logger.info(
                "sentinel relevance pre-gate: empty vocabulary (no macro keywords, no tracked "
                "symbols); gate disabled, analyzing all %d article(s)",
                len(events),
            )
            return events

        relevant = [
            event
            for event in events
            if is_event_relevant(event.title, event.description, vocabulary)
        ]
        dropped = len(events) - len(relevant)
        if dropped:
            logger.info(
                "sentinel relevance pre-gate: dropped %d/%d article(s) before any AI call "
                "(no tracked symbol/name or macro keyword); %d survive to analyze",
                dropped,
                len(events),
                len(relevant),
            )
        return relevant

    async def _route(self, event: EnrichedEvent) -> None:
        """Send one already-important event to the right audience (see class docstring).

        Market-wide broadcast at/above the broadcast floor; otherwise watchlist-targeted. Each
        per-user send is failure-isolated the same way the broadcast loop isolates each chat —
        one recipient failing (or a fake/adapter that raises despite the port's never-raise
        contract) must never abort the rest.
        """
        if event.importance >= self._broadcast_importance_threshold:
            await self._notification_channel.broadcast_event_alert(event)
            return

        symbols = normalize_affected_assets(event.affected_assets, self._instrument_universe)
        if not symbols:
            logger.info(
                "event %s below broadcast floor with no resolvable affected assets; not sent",
                event.id,
            )
            return

        # `sorted` both satisfies the port's `Sequence[str]` (a set is not a Sequence) and makes
        # the emitted query deterministic. `list_trackers_by_symbol` keeps the symbol -> user_ids
        # association (unlike the flat `list_user_ids_tracking`), so each recipient's alert can name
        # WHICH of their tracked assets this event touches.
        trackers_by_symbol = await self._watchlist_repository.list_trackers_by_symbol(
            sorted(symbols)
        )
        if not trackers_by_symbol:
            logger.info(
                "event %s below broadcast floor; no watchlist tracks %s; not sent",
                event.id,
                sorted(symbols),
            )
            return

        # Invert symbol -> {user_ids} into user_id -> {matched symbols}; the recipient set is the
        # union of every symbol's trackers.
        matched_by_user: dict[str, set[str]] = {}
        for symbol, user_ids in trackers_by_symbol.items():
            for user_id in user_ids:
                matched_by_user.setdefault(user_id, set()).add(symbol)

        # One impact blurb per AFFECTED ASSET that at least one recipient watches — the keys of
        # `trackers_by_symbol` — computed once here and shared across every user watching that
        # asset, never re-derived per user.
        asset_impacts = await self._build_asset_impacts(event, trackers_by_symbol.keys())

        delivered = 0
        for user_id, watched in matched_by_user.items():
            watched_symbols = sorted(watched)
            try:
                await self._notification_channel.send_event_alert_to_user(
                    event, user_id, watched_symbols, asset_impacts
                )
                delivered += 1
            except Exception:  # noqa: BLE001 — one bad recipient must not stop the rest
                logger.exception("Failed to send event %s to user %s", event.id, user_id)
        logger.info(
            "event %s delivered to %d/%d watchlist-tracking user(s) for %s",
            event.id,
            delivered,
            len(matched_by_user),
            sorted(symbols),
        )

    async def _build_asset_impacts(
        self, event: EnrichedEvent, assets: Iterable[str]
    ) -> dict[str, str]:
        """Per-asset "why this matters" blurbs for a targeted event, keyed by asset symbol.

        Calls `EventAnalyzerPort.analyze_impact(event, asset)` ONCE per asset (the caller passes
        only assets at least one recipient watches), so the cost is per-(event, asset), never
        per-user: two users watching the same asset reuse the one blurb. Assets whose analysis
        errors or comes back empty are simply omitted — the personalized formatter then falls back
        to a plain "Afecta a X en tu watchlist" line for them.

        Skips impact analysis entirely when the event's own analysis was the unavailable fallback
        (`analysis_available` is False): with no real analyzer behind it there is no genuine impact
        text to produce, so every asset would fall back anyway. Each call is failure-isolated so
        one asset's analyzer error can never abort the scan.
        """
        if not event.analysis_available:
            return {}
        impacts: dict[str, str] = {}
        for asset in assets:
            try:
                text = await self._event_analyzer.analyze_impact(event, asset)
            except Exception:  # noqa: BLE001 — one asset's failure must not abort the scan
                logger.exception("impact analysis failed for asset %s on event %s", asset, event.id)
                continue
            if text and text.strip():
                impacts[asset] = text.strip()
        return impacts

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
