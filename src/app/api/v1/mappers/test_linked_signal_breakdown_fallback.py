"""Unit tests for the breakdown-fallback linked-signal mapper.

Signals are pruned by retention (`SignalRepository.prune_for_instrument`), so a
briefing's `linked_signal_ids` can dangle. When the repository no longer has the
signal but the briefing's own `instrument_breakdown` still records which symbol the
id belonged to, the API must degrade to a partially-resolved row (real symbol,
neutral impact/confidence) instead of the fully-blank "—" sentinel.
"""

from app.api.v1.mappers import linked_signal_from_breakdown
from app.domain.briefing.entities import BriefingInstrumentSection
from app.domain.signals.entities import ImpactClass

_SECTIONS = [
    BriefingInstrumentSection(symbol="AAPL", narrative="n1", signal_ids=["sig-a"]),
    BriefingInstrumentSection(symbol="MSFT", narrative="n2", signal_ids=["sig-b", "sig-c"]),
]


def test_id_found_in_a_section_yields_partial_response_with_real_symbol() -> None:
    response = linked_signal_from_breakdown("sig-c", _SECTIONS)

    assert response is not None
    assert response.signal_id == "sig-c"
    assert response.symbol == "MSFT"
    assert response.impact == ImpactClass.UNCERTAIN.value
    assert response.confidence == 0.0
    assert response.title == ""


def test_id_in_no_section_yields_none_so_caller_can_use_the_missing_sentinel() -> None:
    assert linked_signal_from_breakdown("sig-unknown", _SECTIONS) is None


def test_empty_breakdown_yields_none() -> None:
    assert linked_signal_from_breakdown("sig-a", []) is None
