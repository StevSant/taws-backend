from typing import Any

from app.domain.signals.entities import ImpactClass, Signal, SignalEvidence
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def signal_from_row(row: Any) -> Signal:
    """Map one `signals` table row (as returned by `supabase-py`) onto `Signal`.

    `evidence` is stored as a JSONB array; PostgREST already decodes it into a
    `list[dict]`, so no extra JSON parsing is needed here. Typed `Any` rather than
    `dict[str, Any]` — see `watchlist_row_mapper.py` for why.
    """
    return Signal(
        id=row["id"],
        instrument_symbol=row["instrument_symbol"],
        impact_class=ImpactClass(row["impact_class"]),
        confidence=row["confidence"],
        evidence=[_evidence_from_row(item) for item in row.get("evidence") or []],
        disclaimer=row["disclaimer"],
        locale=row.get("locale") or "",
        thesis=row.get("thesis") or "",
        key_drivers=list(row.get("key_drivers") or []),
        risk_factors=list(row.get("risk_factors") or []),
        # Default True so rows predating the analysis columns (issue #40) read as real
        # analyses rather than being mislabeled "análisis no disponible".
        analysis_available=row.get("analysis_available", True),
        price_delta=row.get("price_delta"),
        created_at=parse_supabase_timestamp(row["created_at"]),
    )


def signal_to_evidence_column(evidence: list[SignalEvidence]) -> list[dict[str, Any]]:
    """Map `Signal.evidence` onto the JSON-serializable shape stored in `signals.evidence`."""
    return [
        {
            "source": item.source,
            "published_at": item.published_at.isoformat(),
            "url": item.url,
            "detail": item.detail,
        }
        for item in evidence
    ]


def _evidence_from_row(item: dict[str, Any]) -> SignalEvidence:
    return SignalEvidence(
        source=item["source"],
        published_at=parse_supabase_timestamp(item["published_at"]),
        url=item.get("url"),
        detail=item.get("detail"),
    )
