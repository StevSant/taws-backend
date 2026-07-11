from app.domain.market.entities import AssetClass
from app.domain.market.ports import InstrumentUniverse

# Bounds how many instruments one scenario fans out to in the Context gathering /
# Quantification steps — same bounding rationale as `generate_briefing.py`'s
# `_MAX_SIGNALS_IN_CONTEXT`: keeps the parallel fetch fan-out and the Synthesis prompt
# small even for a preset (or a free-form request) naming many symbols.
MAX_AFFECTED_SYMBOLS = 5


def resolve_affected_symbols(
    raw_symbols: list[str], instrument_universe: InstrumentUniverse
) -> tuple[list[str], list[AssetClass]]:
    """Validate/dedupe/cap `raw_symbols` against the curated universe, and derive the
    distinct asset classes they belong to.

    Used identically by both intake paths (`build_scenario_spec_from_preset.py` and
    `NormalizeScenarioIntake`'s free-form path) so a `ScenarioSpec`'s
    `affected_asset_classes` is always deterministically derived from
    `affected_symbols` — never independently chosen by a model or trusted verbatim from
    preset JSON — and can never drift out of sync with it.

    Unknown symbols are silently dropped (never raise): a preset row is curated data we
    trust, but a free-form model response might still name a plausible-looking symbol
    that isn't in the tracked universe, and this must degrade gracefully rather than fail
    the whole scenario run over one bad symbol — same "drop, don't crash" ethos as
    `GenerateConsequenceChain._to_edge`'s index clamping.
    """
    resolved_symbols: list[str] = []
    asset_classes: list[AssetClass] = []
    seen_symbols: set[str] = set()
    seen_asset_classes: set[AssetClass] = set()

    for raw_symbol in raw_symbols:
        if len(resolved_symbols) >= MAX_AFFECTED_SYMBOLS:
            break
        symbol = raw_symbol.strip().upper()
        if not symbol or symbol in seen_symbols:
            continue
        instrument = instrument_universe.by_symbol(symbol)
        if instrument is None:
            continue
        seen_symbols.add(symbol)
        resolved_symbols.append(instrument.symbol)
        if instrument.asset_class not in seen_asset_classes:
            seen_asset_classes.add(instrument.asset_class)
            asset_classes.append(instrument.asset_class)

    return resolved_symbols, asset_classes
