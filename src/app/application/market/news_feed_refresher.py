import logging
import time

from app.application.market.use_cases import IngestNews
from app.domain.market.entities import AssetClass

logger = logging.getLogger(__name__)


class NewsFeedRefresher:
    """Throttled, best-effort upstream refresh of the persisted news store (taws#71).

    `GET /api/v1/news` is served DB-first by `ListRecentNews` and never blocks on the
    upstream fan-out. Something still has to *fill* `news_items` — that's this: the news
    router hands each served request to a FastAPI background task, which runs `IngestNews`
    **after the response has already been flushed to the client**. The user's request pays
    nothing for it; the next one gets a warmer store.

    Deliberately in-process (no queue, no cross-instance coordination), like
    `AlertedSignalTracker`. Two guards keep polling clients from stampeding the upstream
    providers, since the radar refetches the feed on an interval and several browsers can
    be open at once:

    - **In-flight dedupe.** A refresh already running for a filter combination is never
      started twice concurrently.
    - **Interval throttle.** After one completes, the same combination won't refresh again
      for `min_interval_seconds`.

    Both are keyed on `(symbol, asset_class, since_hours)`, with the symbol *canonicalized
    against the curated universe by the caller* — so the key space is bounded by the
    universe rather than by whatever arbitrary `?symbol=` strings arrive.

    Failures are swallowed and logged: a refresh that dies must never surface to a client
    whose response was already sent successfully.
    """

    def __init__(
        self,
        ingest_news: IngestNews,
        min_interval_seconds: float,
        limit: int,
    ) -> None:
        self._ingest_news = ingest_news
        self._min_interval_seconds = min_interval_seconds
        self._limit = limit
        self._last_refresh_at: dict[tuple[str | None, str | None, int], float] = {}
        self._in_flight: set[tuple[str | None, str | None, int]] = set()

    async def refresh(
        self,
        symbol: str | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
    ) -> None:
        """Run one upstream ingest for this filter combination, unless throttled or already
        in flight. Awaited by the caller (a background task), never by a request handler."""
        key = (symbol, asset_class.value if asset_class else None, since_hours)
        if not self._may_refresh(key):
            return

        self._in_flight.add(key)
        try:
            await self._ingest_news.execute(
                symbols=[symbol] if symbol else None,
                asset_class=asset_class,
                since_hours=since_hours,
                limit=self._limit,
            )
        except Exception:
            logger.warning("Background news refresh failed for %s.", key, exc_info=True)
        finally:
            # Stamped even on failure, so a persistently broken upstream is retried on the
            # throttle interval rather than on every single request.
            self._last_refresh_at[key] = time.monotonic()
            self._in_flight.discard(key)

    def _may_refresh(self, key: tuple[str | None, str | None, int]) -> bool:
        if key in self._in_flight:
            return False
        last = self._last_refresh_at.get(key)
        return last is None or (time.monotonic() - last) >= self._min_interval_seconds
