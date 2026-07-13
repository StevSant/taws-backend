from abc import ABC, abstractmethod

from app.domain.sentiment.entities import SentimentReading


class SentimentRepository(ABC):
    """Port for persisting Sentiment Analyst readings (issue #29).

    New with the shared-analysis cache. Sentiment used to be recomputed on every call and
    thrown away — `AnalyzeSentiment` returned a `SentimentReading` that was never written
    anywhere — so N users asking about AAPL paid for N identical LLM tone scores. Caching it
    requires persisting it first; this port is that missing half.

    Same visibility model as `SignalRepository`/`ScenarioRepository`: a tone score is
    market analysis about an instrument, NOT per-user data. `sentiment_readings` therefore
    has no `user_id`, is written with the service-role key, and is readable by any
    authenticated user (migration `0015`). No trading/execution fields exist.

    Deliberately a separate port from `FearGreedProvider` (the other thing in
    `domain/sentiment/ports/`): that one *fetches* a market-wide index from a vendor, this
    one *persists* per-instrument readings — different responsibilities, different adapters,
    per the repo's "one port, one responsibility" rule.
    """

    @abstractmethod
    async def create(self, reading: SentimentReading) -> SentimentReading:
        """Create a new sentiment reading and return it as persisted."""
        raise NotImplementedError

    @abstractmethod
    async def get_latest_for_instrument(
        self, symbol: str, locale: str
    ) -> SentimentReading | None:
        """Return the newest reading for `(symbol, locale)`, or `None` if there is none.

        Single `order by created_at desc limit 1` — the freshness-cache lookup. `locale` is
        part of the key because `rationale` is localized; see `SentimentReading.locale`.
        """
        raise NotImplementedError

    @abstractmethod
    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        """Delete all but the `keep` newest readings for `(symbol, locale)`; return how many
        rows were deleted. Same bounded-growth rationale as
        `SignalRepository.prune_for_instrument`."""
        raise NotImplementedError
