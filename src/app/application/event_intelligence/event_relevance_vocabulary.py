import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventRelevanceVocabulary:
    """A precompiled, case-insensitive whole-word/phrase matcher over a fixed set of terms.

    Built once per Sentinel scan (see `build_event_relevance_vocabulary`) from the union of every
    watchlist's symbols and company names plus the macro keyword list, then queried per article by
    `is_event_relevant`. Matching is on word boundaries (a regex word-boundary anchor), so a short
    ticker like "IT" can't fire inside "hospitality", and multi-word terms ("Federal Reserve")
    match as phrases regardless of the whitespace between their words. A vocabulary built from no
    non-blank terms `is_empty` and matches nothing — the caller reads that as "gate disabled"
    rather than "drop everything".
    """

    pattern: re.Pattern[str] | None
    size: int

    @property
    def is_empty(self) -> bool:
        """True when no term was supplied — the caller should skip the gate, not apply it."""
        return self.pattern is None

    def matches(self, text: str) -> bool:
        """True when `text` contains any vocabulary term on a whole-word/phrase boundary."""
        if self.pattern is None:
            return False
        return self.pattern.search(text) is not None

    @classmethod
    def build(cls, terms: Iterable[str]) -> "EventRelevanceVocabulary":
        """Compile `terms` into one case-insensitive alternation regex.

        Blank terms and case-insensitive duplicates are dropped; internal whitespace inside a term
        is treated as "one or more spaces" so a phrase matches regardless of spacing. Each term is
        `re.escape`-d so tickers/names carrying regex metacharacters ("AT&T", "BRK.B") match
        literally. Longer alternatives are tried first, so a multi-word phrase wins over a single
        word it contains. Returns an empty (matches-nothing) vocabulary when no term survives.
        """
        alternatives: list[str] = []
        seen: set[str] = set()
        for term in terms:
            collapsed = " ".join(term.split())
            if not collapsed:
                continue
            key = collapsed.lower()
            if key in seen:
                continue
            seen.add(key)
            words = [re.escape(word) for word in collapsed.split(" ")]
            alternatives.append(r"\s+".join(words))
        if not alternatives:
            return cls(pattern=None, size=0)
        alternatives.sort(key=len, reverse=True)
        pattern = re.compile(rf"\b(?:{'|'.join(alternatives)})\b", re.IGNORECASE)
        return cls(pattern=pattern, size=len(alternatives))
