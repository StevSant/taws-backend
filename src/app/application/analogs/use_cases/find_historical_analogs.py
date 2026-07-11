import logging
from datetime import UTC, datetime
from typing import Any

from app.application.analogs.build_analog_text import build_analog_text
from app.domain.agents.ports import EmbeddingProvider, VectorStore
from app.domain.signals.entities import ImpactClass, SignalEvidence

logger = logging.getLogger(__name__)

_ANALOG_TAG = "[análogo histórico]"
_DEFAULT_TOP_K = 3


class FindHistoricalAnalogs:
    """Retrieval use case (issue #15): given a new signal-in-progress (instrument + impact
    class + a short event summary), embed it and search the `VectorStore` for the most similar
    past events, returning them as `[análogo histórico]`-tagged `SignalEvidence` entries.

    Built as a standalone, reusable use case — deliberately NOT inlined into
    `GenerateSignal` — so it can also be called from the Scenario engine's context-gathering
    step once issue #12 builds it (that step doesn't exist yet; this is the integration point
    its author should call). See `execute()`'s signature below and `IndexSignalAnalog` (same
    package) for the companion write path that populates the vector store.

    Simplification (documented, not a bug): "realized outcome" for T1 scope is the
    `price_delta` already computed at signal-generation time (see `IndexSignalAnalog`) — a
    proxy for "what happened around this kind of event," not a true forward-looking
    realized-return pipeline (which would require tracking price *after* the signal, not *at*
    it). Building a full outcome-tracking system is out of scope here; if/when one lands, only
    `IndexSignalAnalog`'s metadata shape needs to change, not this retrieval path.

    Filtering note: `VectorStore.search()` is a generic top-k-nearest port with no filter
    parameter, so this searches across all instruments/asset classes, not just the queried
    instrument — a deliberate simplification consistent with "historical analog" meaning
    "a similar market situation," which need not be the same instrument. `instrument_symbol` is
    still stored per-row for future filtering/debugging if a scoped search is added later.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        top_k: int = _DEFAULT_TOP_K,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._top_k = top_k

    async def execute(
        self, instrument_symbol: str, impact_class: ImpactClass, summary: str
    ) -> list[SignalEvidence]:
        """Return up to `top_k` historical-analog evidence entries for a new signal-in-progress.

        `summary` is a short natural-language description of the event driving the new signal
        (e.g. the top news headline) — embedded via the same `build_analog_text` shape
        `IndexSignalAnalog` uses at write time, so semantically similar past events surface.

        Never raises on embedding/vector-store failures (e.g. no `OPENAI_API_KEY`, no
        `DATABASE_URL`, or an empty/uninitialized store) — a broken RAG path degrades to "no
        analogs" (empty list), the same broad-catch-and-degrade shape as
        `GenerateSignal._classify_impact`/`_compute_price_delta`.
        """
        try:
            query_text = build_analog_text(instrument_symbol, impact_class, summary)
            [query_vector] = await self._embedding_provider.embed([query_text])
            matches = await self._vector_store.search(query_vector, top_k=self._top_k)
        except Exception:
            logger.warning(
                "Historical analog retrieval failed for %s; returning no analogs.",
                instrument_symbol,
                exc_info=True,
            )
            return []

        evidence = [_to_evidence(match) for match in matches]
        return [item for item in evidence if item is not None]


def _to_evidence(match: dict[str, Any]) -> SignalEvidence | None:
    metadata = match.get("metadata") or {}
    summary = metadata.get("summary")
    if not summary:
        return None

    instrument_symbol = metadata.get("instrument_symbol", "?")
    impact_class = metadata.get("impact_class", ImpactClass.UNCERTAIN.value)
    price_delta = metadata.get("price_delta")
    outcome = (
        f", realized price_delta {price_delta:+.2f}%"
        if isinstance(price_delta, int | float)
        else ""
    )
    detail = f"{_ANALOG_TAG} {instrument_symbol} ({impact_class}){outcome}: {summary}"

    return SignalEvidence(
        source=_ANALOG_TAG,
        published_at=_parse_created_at(metadata.get("created_at")),
        url=None,
        detail=detail,
    )


def _parse_created_at(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(UTC)
