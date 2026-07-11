from app.domain.scenario.entities import EvidenceType

_EVIDENCE_TAG_LABELS: dict[EvidenceType, str] = {
    EvidenceType.ACTUAL_DATA: "[dato actual]",
    EvidenceType.HISTORICAL_ANALOG: "[análogo histórico]",
    EvidenceType.REASONING: "[razonamiento]",
}


def format_scenario_evidence(evidence_type: EvidenceType, text: str) -> str:
    """Prefix `text` with its grounding-policy bracket tag, e.g. `"[dato actual] ..."`.

    The single place that owns the issue's exact grounding-policy tag literals, so every
    `ScenarioEvidence.detail` is formatted identically regardless of which step produced
    it (context gathering, quantification, or the Synthesis LLM's own reasoning) — same
    "code owns presentation formatting, never trust the model to format it" discipline as
    `application/analogs/build_analog_text.py`'s `_ANALOG_TAG`.
    """
    return f"{_EVIDENCE_TAG_LABELS[evidence_type]} {text}"
