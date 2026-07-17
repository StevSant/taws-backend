from collections.abc import Sequence

from app.domain.market.ports import InstrumentUniverse


def normalize_affected_assets(assets: Sequence[str], universe: InstrumentUniverse) -> set[str]:
    """Map free-form affected-asset strings to canonical uppercase watchlist symbols.

    Gemini's `affected_assets` are free-form ("BTC", "Bitcoin", "oil"); watchlist items are
    stored as canonical uppercase symbols (the add-item router uppercases before insert). For
    each asset, resolve it through the instrument universe (`by_symbol`, case-insensitive) and
    use the universe's canonical symbol when it matches; otherwise fall back to the trimmed,
    uppercased string, so a literal ticker like "BTC" still matches a watchlist "BTC" even for
    assets outside the curated universe. Blank entries are skipped and the result is a set, so
    duplicates collapse — this is the comparison key `BroadcastImportantEvents` hands to
    `WatchlistRepository.list_user_ids_tracking`.
    """
    normalized: set[str] = set()
    for asset in assets:
        if not asset or not asset.strip():
            continue
        instrument = universe.by_symbol(asset)
        normalized.add(instrument.symbol.upper() if instrument else asset.strip().upper())
    return normalized
