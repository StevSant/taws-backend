"""Cover for the Sentinel relevance pre-gate's vocabulary + matcher.

Drives the real `build_event_relevance_vocabulary` (assembles the two tracks) and the
`is_event_relevant` matcher (word-boundary, case-insensitive) via a tiny fake `InstrumentUniverse`.
Per `backend/CLAUDE.md`: a minimal targeted test next to the behavior, not a broad suite.
"""

from app.application.event_intelligence import (
    build_event_relevance_vocabulary,
    is_event_relevant,
)
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse


class _FakeUniverse(InstrumentUniverse):
    """Maps symbol -> canonical name; a symbol absent from the map resolves to `None`."""

    def __init__(self, names: dict[str, str]) -> None:
        self._by_symbol = {
            symbol.upper(): Instrument(
                symbol=symbol.upper(), name=name, asset_class=AssetClass.STOCK, currency="USD"
            )
            for symbol, name in names.items()
        }

    def all(self) -> list[Instrument]:
        return list(self._by_symbol.values())

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._by_symbol.values() if i.asset_class == asset_class]


def test_symbol_matches_on_word_boundary_not_substring() -> None:
    vocabulary = build_event_relevance_vocabulary(
        ["TSLA"], _FakeUniverse({"TSLA": ""}), [], min_symbol_match_length=3
    )
    assert is_event_relevant("TSLA rallied today", "", vocabulary)
    # Word boundary: the ticker must not fire inside a longer token.
    assert not is_event_relevant("the TSLAX fund gained", "", vocabulary)
    assert not is_event_relevant("nothing relevant in this headline", "", vocabulary)


def test_symbol_outside_the_universe_still_matches_as_a_bare_ticker() -> None:
    vocabulary = build_event_relevance_vocabulary(
        ["ABCD"], _FakeUniverse({}), [], min_symbol_match_length=3
    )
    assert is_event_relevant("ABCD announced a merger", "", vocabulary)


def test_company_name_matches_even_when_the_ticker_is_absent() -> None:
    vocabulary = build_event_relevance_vocabulary(
        ["NVDA"], _FakeUniverse({"NVDA": "Nvidia"}), [], min_symbol_match_length=3
    )
    assert is_event_relevant("Nvidia earnings beat expectations", "", vocabulary)
    assert is_event_relevant("NVDA jumped after hours", "", vocabulary)


def test_macro_keyword_phrase_matches_as_a_phrase() -> None:
    vocabulary = build_event_relevance_vocabulary(
        [], _FakeUniverse({}), ["Federal Reserve", "Fed"], min_symbol_match_length=3
    )
    assert is_event_relevant("the Federal Reserve met today", "", vocabulary)
    # Any run of whitespace between the words of a phrase still matches.
    assert is_event_relevant("markets await the Federal  Reserve", "", vocabulary)
    # A single-word macro keyword matches on its own word boundary.
    assert is_event_relevant("Fed hikes rates", "", vocabulary)


def test_article_hitting_no_track_is_not_relevant() -> None:
    vocabulary = build_event_relevance_vocabulary(
        ["NVDA"], _FakeUniverse({"NVDA": "Nvidia"}), ["inflation"], min_symbol_match_length=3
    )
    assert not is_event_relevant(
        "local sports team wins the championship", "the weather is nice", vocabulary
    )


def test_matching_is_case_insensitive_across_both_channels() -> None:
    vocabulary = build_event_relevance_vocabulary(
        ["NVDA"], _FakeUniverse({"NVDA": "Nvidia"}), ["Federal Reserve"], min_symbol_match_length=3
    )
    # Lowercase text still matches the mixed-case vocabulary.
    assert is_event_relevant("nvidia and the federal reserve", "", vocabulary)
    # The description channel is matched too, not just the title.
    assert is_event_relevant("", "NVDA mentioned only in the description", vocabulary)


def test_short_ticker_does_not_false_match_a_common_word() -> None:
    # "IT" (Gartner) is length 2 < 3, so it is NOT added as a bare ticker; only its name is.
    vocabulary = build_event_relevance_vocabulary(
        ["IT"], _FakeUniverse({"IT": "Gartner"}), [], min_symbol_match_length=3
    )
    assert not is_event_relevant("it was a great day for the market", "", vocabulary)
    # Recall is preserved: the company name still matches.
    assert is_event_relevant("Gartner released a report", "", vocabulary)
    # Prove the length guard is what prevented the false match: at min length 2, bare "IT"
    # WOULD fire on the article word "it".
    permissive = build_event_relevance_vocabulary(
        ["IT"], _FakeUniverse({"IT": "Gartner"}), [], min_symbol_match_length=2
    )
    assert is_event_relevant("it was a great day for the market", "", permissive)


def test_empty_vocabulary_is_gate_disabled_and_matches_nothing() -> None:
    vocabulary = build_event_relevance_vocabulary(
        [], _FakeUniverse({}), [], min_symbol_match_length=3
    )
    assert vocabulary.is_empty
    assert not is_event_relevant("anything at all here", "", vocabulary)
