"""Unit cover for `normalize_affected_assets` — the free-form-asset -> canonical-symbol map
that lets the Sentinel scan's watchlist-targeted routing compare Gemini's free-form
`affected_assets` against uppercased watchlist symbols.

Per `backend/CLAUDE.md`: a minimal targeted test next to the behavior under test, not the start
of a broad suite.
"""

from app.application.event_intelligence import normalize_affected_assets
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse


class _FakeUniverse(InstrumentUniverse):
    """Resolves a fixed set of canonical symbols; everything else is unknown."""

    def __init__(self, known_symbols: list[str]) -> None:
        self._by_symbol = {
            symbol.upper(): Instrument(
                symbol=symbol.upper(),
                name=symbol,
                asset_class=AssetClass.CRYPTO,
                currency="USD",
            )
            for symbol in known_symbols
        }

    def all(self) -> list[Instrument]:
        return list(self._by_symbol.values())

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._by_symbol.values() if i.asset_class == asset_class]


def test_resolves_known_symbol_to_its_canonical_uppercase_form() -> None:
    universe = _FakeUniverse(["BTC"])

    assert normalize_affected_assets(["btc"], universe) == {"BTC"}


def test_falls_back_to_trimmed_uppercase_for_unresolved_strings() -> None:
    universe = _FakeUniverse([])

    # Neither is in the universe -> literal fallback, so a bare ticker still matches a watchlist.
    assert normalize_affected_assets([" eth ", "oil"], universe) == {"ETH", "OIL"}


def test_skips_blank_entries_and_collapses_duplicates() -> None:
    universe = _FakeUniverse(["BTC"])

    assert normalize_affected_assets(["btc", "BTC", "", "   "], universe) == {"BTC"}


def test_empty_input_yields_empty_set() -> None:
    assert normalize_affected_assets([], _FakeUniverse(["BTC"])) == set()
