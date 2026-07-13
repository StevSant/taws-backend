from typing import Any

from app.domain.sentiment.entities import (
    FearGreedClassification,
    FearGreedReading,
    SentimentLabel,
    SentimentReading,
)
from app.domain.signals.entities import SignalEvidence
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def sentiment_reading_to_row(reading: SentimentReading) -> dict[str, Any]:
    """Map a `SentimentReading` onto the shape stored in `sentiment_readings` (issue #29).

    `evidence` and `fear_greed` are JSONB — the same "JSONB for a structured nested shape"
    choice `signals.evidence` and `scenarios.spec` already make.

    `fear_greed` is persisted rather than re-fetched on read (the design spec's column list
    omitted it): a repository that had to reach for a `FearGreedProvider` to rehydrate a
    complete entity would be an adapter depending on another port, and a cached reading
    should return exactly the reading that was cached — not last week's tone score glued to
    today's index value.
    """
    return {
        "id": reading.id,
        "instrument_symbol": reading.instrument_symbol,
        "locale": reading.locale,
        "tone_score": reading.tone_score,
        "tone_label": reading.tone_label.value,
        "fear_greed": {
            "value": reading.fear_greed.value,
            "classification": reading.fear_greed.classification.value,
            "as_of": reading.fear_greed.as_of.isoformat(),
        },
        "evidence": [
            {
                "source": item.source,
                "published_at": item.published_at.isoformat(),
                "url": item.url,
                "detail": item.detail,
            }
            for item in reading.evidence
        ],
        "rationale": reading.rationale,
        "disclaimer": reading.disclaimer,
        "created_at": reading.created_at.isoformat(),
    }


def sentiment_reading_from_row(row: Any) -> SentimentReading:
    """Map one `sentiment_readings` row (as returned by `supabase-py`) onto `SentimentReading`.

    JSONB columns are already decoded into `dict`/`list` by PostgREST, so no extra JSON
    parsing is needed here. Typed `Any` rather than `dict[str, Any]` — see
    `watchlist_row_mapper.py` for why.
    """
    fear_greed = row["fear_greed"]
    return SentimentReading(
        id=row["id"],
        instrument_symbol=row["instrument_symbol"],
        tone_score=float(row["tone_score"]),
        tone_label=SentimentLabel(row["tone_label"]),
        fear_greed=FearGreedReading(
            value=int(fear_greed["value"]),
            classification=FearGreedClassification(fear_greed["classification"]),
            as_of=parse_supabase_timestamp(fear_greed["as_of"]),
        ),
        evidence=[_evidence_from_row(item) for item in row.get("evidence") or []],
        rationale=row["rationale"],
        disclaimer=row["disclaimer"],
        locale=row.get("locale") or "",
        created_at=parse_supabase_timestamp(row["created_at"]),
    )


def _evidence_from_row(item: dict[str, Any]) -> SignalEvidence:
    return SignalEvidence(
        source=item["source"],
        published_at=parse_supabase_timestamp(item["published_at"]),
        url=item.get("url"),
        detail=item.get("detail"),
    )
