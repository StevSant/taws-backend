"""`ScoreNewsSentiment` fills `news_items.sentiment_score` — the column with no producer.

Before this pass existed, the ONLY writer of `sentiment_score` was a pass-through of Marketaux's
own per-entity number (`marketaux_article_mapper.py`). Every other adapter — SEC EDGAR, RSS,
NewsAPI, Finnhub — built a `NewsItem` without it, so 2,276 of 2,278 rows sat at NULL and the UI
rendered them "Sin clasificar". The step did not exist; these tests are its contract.

The hallucination test is the important one: the model addresses articles POSITIONALLY, so a
returned index outside the chunk must be dropped, never clamped onto a neighbouring row. A wrong
score is worse than no score — NULL is honestly "unclassified", a fabricated number is
indistinguishable from a real rating.
"""

from datetime import UTC, datetime
from typing import Any

from app.application.market.use_cases import ScoreNewsSentiment
from app.domain.market.entities import NewsItem


def _item(news_id: str, title: str = "A headline") -> NewsItem:
    return NewsItem(
        id=news_id,
        title=title,
        summary="A summary.",
        url=f"https://example.test/{news_id}",
        source="Example",
        provider="sec_edgar",
        published_at=datetime(2026, 7, 13, tzinfo=UTC),
    )


class _FakeRepository:
    """Only the two methods `ScoreNewsSentiment` touches; records what was written."""

    def __init__(self, unscored: list[NewsItem]) -> None:
        self._unscored = unscored
        self.saved: dict[str, float] = {}
        self.requested_limit: int | None = None

    async def list_unscored(self, limit: int) -> list[NewsItem]:
        self.requested_limit = limit
        return self._unscored[:limit]

    async def save_sentiment_scores(self, scores_by_id: dict[str, float]) -> None:
        self.saved.update(scores_by_id)


class _FakeLLM:
    """Returns a canned structured payload, or raises to simulate an unavailable provider."""

    def __init__(self, payload: dict[str, Any] | None = None, raises: bool = False) -> None:
        self._payload = payload
        self._raises = raises
        self.calls = 0

    async def complete_structured(self, messages, schema, schema_name):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self._raises:
            raise RuntimeError("no OPENAI_API_KEY configured")
        return self._payload


def _build(
    unscored: list[NewsItem], llm: _FakeLLM, *, batch_size: int = 60, chunk_size: int = 15
) -> tuple[ScoreNewsSentiment, _FakeRepository]:
    repository = _FakeRepository(unscored)
    use_case = ScoreNewsSentiment(
        news_item_repository=repository,  # type: ignore[arg-type]
        llm_provider=llm,  # type: ignore[arg-type]
        batch_size=batch_size,
        chunk_size=chunk_size,
    )
    return use_case, repository


async def test_scores_every_article_the_model_rated() -> None:
    items = [_item("a"), _item("b"), _item("c")]
    llm = _FakeLLM(
        {
            "scores": [
                {"index": 0, "score": 0.8},
                {"index": 1, "score": -0.6},
                {"index": 2, "score": 0.0},
            ]
        }
    )
    use_case, repository = _build(items, llm)

    result = await use_case.execute()

    assert repository.saved == {"a": 0.8, "b": -0.6, "c": 0.0}
    assert result.scored == 3
    assert result.failed == 0


async def test_batches_many_articles_into_one_llm_call_per_chunk() -> None:
    items = [_item(str(n)) for n in range(10)]
    llm = _FakeLLM({"scores": [{"index": 0, "score": 0.1}]})
    use_case, _ = _build(items, llm, chunk_size=4)

    await use_case.execute()

    # 10 articles / chunk of 4 => 3 calls, NOT 10. The whole point of batching.
    assert llm.calls == 3


async def test_a_hallucinated_index_is_dropped_not_written_to_another_row() -> None:
    items = [_item("a"), _item("b")]
    llm = _FakeLLM(
        {
            "scores": [
                {"index": 0, "score": 0.5},
                {"index": 99, "score": -1.0},  # does not exist in this chunk
            ]
        }
    )
    use_case, repository = _build(items, llm)

    await use_case.execute()

    assert repository.saved == {"a": 0.5}
    assert "b" not in repository.saved  # left NULL, retried next tick — never mis-assigned


async def test_an_llm_failure_leaves_the_chunk_unscored_instead_of_raising() -> None:
    items = [_item("a"), _item("b")]
    use_case, repository = _build(items, _FakeLLM(raises=True))

    result = await use_case.execute()  # must not raise — the tick has to survive

    assert repository.saved == {}
    assert result.failed == 2
    assert result.scored == 0


async def test_one_bad_chunk_does_not_abandon_the_rest_of_the_batch() -> None:
    items = [_item(str(n)) for n in range(4)]

    class _FailsFirstChunk(_FakeLLM):
        async def complete_structured(self, messages, schema, schema_name):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")
            return {"scores": [{"index": 0, "score": 0.3}, {"index": 1, "score": 0.4}]}

    use_case, repository = _build(items, _FailsFirstChunk(), chunk_size=2)

    result = await use_case.execute()

    # Chunk 1 (items 0,1) failed; chunk 2 (items 2,3) still got scored.
    assert repository.saved == {"2": 0.3, "3": 0.4}
    assert result.failed == 2
    assert result.scored == 2


async def test_an_empty_backlog_makes_no_llm_call() -> None:
    llm = _FakeLLM({"scores": []})
    use_case, repository = _build([], llm)

    result = await use_case.execute()

    assert llm.calls == 0
    assert repository.saved == {}
    assert result.considered == 0


async def test_the_batch_limit_bounds_the_pass() -> None:
    items = [_item(str(n)) for n in range(100)]
    llm = _FakeLLM({"scores": []})
    use_case, repository = _build(items, llm, batch_size=10)

    await use_case.execute()

    assert repository.requested_limit == 10
