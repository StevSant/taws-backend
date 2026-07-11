import logging

from app.application.analogs.build_analog_text import build_analog_text
from app.domain.agents.ports import EmbeddingProvider, VectorStore
from app.domain.signals.entities import Signal

logger = logging.getLogger(__name__)


class IndexSignalAnalog:
    """Write-path counterpart to `FindHistoricalAnalogs` (issue #15): embeds a just-generated
    `Signal` and upserts it into the `VectorStore`, so it becomes retrievable as a historical
    analog for future signals.

    Called by `GenerateSignal.execute` right after a `Signal` is persisted (see
    `generate_signal.py`'s historical-analogs block). Metadata captures `price_delta` as the
    "realized outcome" proxy for T1 scope — see `FindHistoricalAnalogs`'s docstring for why
    that's a deliberate simplification, not a full outcome-tracking pipeline.

    Never raises: indexing is a side effect of persisting a signal, not a precondition for it,
    so an embedding/vector-store failure here must never fail signal generation — same
    broad-catch-and-degrade shape used throughout this pipeline.
    """

    def __init__(self, embedding_provider: EmbeddingProvider, vector_store: VectorStore) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def execute(self, signal: Signal, summary: str) -> None:
        try:
            text = build_analog_text(signal.instrument_symbol, signal.impact_class, summary)
            [vector] = await self._embedding_provider.embed([text])
            await self._vector_store.upsert(
                ids=[signal.id],
                vectors=[vector],
                metadata=[
                    {
                        "instrument_symbol": signal.instrument_symbol,
                        "impact_class": signal.impact_class.value,
                        "summary": summary,
                        "price_delta": signal.price_delta,
                        "created_at": signal.created_at.isoformat(),
                    }
                ],
            )
        except Exception:
            logger.warning(
                "Historical analog indexing failed for signal %s; skipping.",
                signal.id,
                exc_info=True,
            )
