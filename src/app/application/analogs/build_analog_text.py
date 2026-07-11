from app.domain.signals.entities import ImpactClass


def build_analog_text(instrument_symbol: str, impact_class: ImpactClass, summary: str) -> str:
    """Build the canonical text representation embedded for one historical-analog event.

    Used identically by `IndexSignalAnalog` (write path, embeds a just-generated `Signal`) and
    `FindHistoricalAnalogs` (read path, embeds a new signal-in-progress) — the same text shape
    must be used on both sides for cosine similarity between the resulting embeddings to be
    meaningful.
    """
    return f"{instrument_symbol} | {impact_class.value} | {summary}"
