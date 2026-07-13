import logging

from app.application.market.news_sentiment_batch import NewsSentimentBatch
from app.application.market.sentiment_scoring_result import SentimentScoringResult
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.market.entities import NewsItem
from app.domain.market.ports import NewsItemRepository

logger = logging.getLogger(__name__)

_SCHEMA_NAME = "news_sentiment_batch"

_SYSTEM_PROMPT = """You are a financial news sentiment rater.

For EACH numbered article you are given, score the tone of that article as market news, from \
-1.0 (very negative) to +1.0 (very positive). Judge the article on its own terms — the tone of \
the event it reports, not whether you personally consider it important.

Guidance:
- If the article is NOT market or business news (crime, sport, human interest, general \
politics with no stated market angle), score it exactly 0.0. You are rating market tone, not \
whether the events described are good or bad for the world. A reassuring statement about a \
non-financial event is still 0.0.
- Routine, procedural, or purely administrative filings (a change of registrar, a scheduled \
8-K, a director's planned retirement) are NEUTRAL — score them near 0.0.
- Score near 0.0 when the headline is ambiguous or you cannot tell. Never guess a direction \
just to look decisive; an honest 0.0 is more useful than a confident wrong sign.
- Judge ONLY from the title and summary provided. Never use outside knowledge about the \
company, and never invent facts that are not in the text.

Return exactly one entry per article, addressed by its 0-based index."""


class ScoreNewsSentiment:
    """Fill in `news_items.sentiment_score` — the column the UI's sentiment badge reads.

    Why this exists: `sentiment_score` had exactly ONE producer in the whole codebase — a
    pass-through of Marketaux's own per-entity number in `marketaux_article_mapper.py`. Every
    other adapter (SEC EDGAR, RSS, NewsAPI, Finnhub) constructs a `NewsItem` without it, so the
    column stayed NULL forever and the UI rendered ~99.9% of the corpus as "Sin clasificar".
    Marketaux is also the most rate-limited provider in the fan-out, so the one source that
    could score was contributing a couple of articles while the free, unlimited ones supplied
    thousands that structurally could not. This is not a broken job — the step did not exist.

    Note what this is NOT. `AnalyzeSentiment` (`application/sentiment/`) is a real LLM pipeline
    and it looks like it covers this, which is exactly why the gap survived so long: it scores
    an INSTRUMENT's news tone and writes the `sentiment_readings` table. It never touches an
    article's own `sentiment_score`. Per-instrument tone and per-article tone are different
    questions and they live in different tables.

    Runs as a scheduled pass over unscored rows rather than inline in `IngestNews`, which buys
    two things for one mechanism: newly-ingested items get scored on the next tick, and the
    thousands of rows already sitting at NULL get backfilled by the same code path — no
    separate one-shot migration script that rots the moment it's run.

    Never raises. A chunk whose LLM call fails is logged and left unscored, so it is simply
    retried on the next tick; one bad chunk must not abandon the rest of the batch.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        llm_provider: LLMProvider,
        batch_size: int,
        chunk_size: int,
    ) -> None:
        self._news_item_repository = news_item_repository
        self._llm_provider = llm_provider
        self._batch_size = max(1, batch_size)
        self._chunk_size = max(1, chunk_size)

    async def execute(self) -> SentimentScoringResult:
        """Score up to `batch_size` unscored articles, in chunks of `chunk_size` per LLM call."""
        unscored = await self._news_item_repository.list_unscored(self._batch_size)
        if not unscored:
            return SentimentScoringResult(considered=0, scored=0, failed=0)

        scores: dict[str, float] = {}
        failed = 0
        for start in range(0, len(unscored), self._chunk_size):
            chunk = unscored[start : start + self._chunk_size]
            chunk_scores = await self._score_chunk(chunk)
            if chunk_scores is None:
                failed += len(chunk)
                continue
            scores.update(chunk_scores)

        if scores:
            await self._news_item_repository.save_sentiment_scores(scores)

        logger.info(
            "News sentiment tick: %d considered, %d scored, %d failed.",
            len(unscored),
            len(scores),
            failed,
        )
        return SentimentScoringResult(considered=len(unscored), scored=len(scores), failed=failed)

    async def _score_chunk(self, chunk: list[NewsItem]) -> dict[str, float] | None:
        """Score one chunk; `None` when the LLM call failed and the chunk should be retried.

        The model addresses articles by position, so an index outside this chunk is a
        hallucination and is DROPPED rather than clamped — writing a fabricated score onto a
        real row would be worse than leaving it NULL, because NULL is honestly "unclassified"
        while a wrong number is indistinguishable from a real rating. Anything it omits simply
        stays NULL and comes back around on the next tick.
        """
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                    Message(role=MessageRole.USER, content=_format_articles(chunk)),
                ],
                schema=NewsSentimentBatch.model_json_schema(),
                schema_name=_SCHEMA_NAME,
            )
            batch = NewsSentimentBatch.model_validate(raw)
        except Exception:
            # `complete_structured` raises with no OPENAI_API_KEY configured, and a malformed
            # response raises in `.model_validate`. Either way the chunk stays NULL and is
            # picked up again next tick — the same "degrade, never crash the pass" posture as
            # `AnalyzeSentiment._classify_tone` and `RefreshTrackedAnalysis._isolated`.
            logger.warning(
                "Sentiment scoring failed for a chunk of %d article(s); leaving them unscored.",
                len(chunk),
                exc_info=True,
            )
            return None

        return {
            chunk[entry.index].id: entry.score
            for entry in batch.scores
            if 0 <= entry.index < len(chunk)
        }


def _format_articles(chunk: list[NewsItem]) -> str:
    """Render the chunk as a numbered list — the indices the model scores against."""
    lines = []
    for index, item in enumerate(chunk):
        summary = item.summary.strip()
        lines.append(f"[{index}] {item.title.strip()}")
        if summary:
            lines.append(f"    {summary}")
    return "\n".join(lines)
