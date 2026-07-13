from app.domain.event_intelligence.entities import NewsEvent


class ProcessedEventTracker:
    """Remembers which news events the Sentinel scan has already run through Gemini.

    Two jobs, both essential the moment the scan became a scheduled poll rather than a manual
    button:

    1. **Don't pay twice.** A poller re-fetches an overlapping window every tick (a headline
       published 10 minutes ago is still in a 6-hour window on the next run). Without this,
       every tick would re-send the same articles to Gemini — a recurring, unbounded token
       bill for zero new information.
    2. **Don't notify twice.** The same article would otherwise clear the importance gate on
       every tick and be broadcast to every linked chat again, forever. That is precisely the
       kind of repeat-notification spam the Watchdog's own alert path already had to be fixed
       for (see `AlertedSignalTracker`).

    Keyed on the article URL where present, falling back to the title: URLs are the only stable
    identifier the upstream providers agree on, but RSS/EDGAR items occasionally arrive without
    one, and a title collision is a far better failure than a duplicate broadcast.

    In-process, like `AlertedSignalTracker` — it resets on restart, so a fresh deploy may
    re-analyze (and potentially re-alert on) the current window once. Accepted at this scope;
    the natural upgrade is persisting these keys alongside the enriched events.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_new(self, event: NewsEvent) -> bool:
        return _key(event) not in self._seen

    def mark_processed(self, event: NewsEvent) -> None:
        """Record that this event has been analyzed — called whether or not it was important
        enough to notify anyone about, since re-analyzing a known-unimportant article on the
        next tick costs exactly as much as re-analyzing an important one."""
        self._seen.add(_key(event))


def _key(event: NewsEvent) -> str:
    return event.url or event.title
