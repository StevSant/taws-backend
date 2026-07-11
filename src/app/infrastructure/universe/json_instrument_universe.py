from pathlib import Path

from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse
from app.infrastructure.seeds import load_universe_seed


class JsonInstrumentUniverse(InstrumentUniverse):
    """InstrumentUniverse adapter backed by the packaged `universe.json` seed.

    Parsed and indexed once at construction time (cached at load) — `all()`,
    `by_symbol()`, and `by_asset_class()` are then plain in-memory lookups.
    """

    def __init__(self, seed_path: Path) -> None:
        self._instruments = self._build_instruments(seed_path)
        self._by_symbol = {item.symbol.upper(): item for item in self._instruments}

    def all(self) -> list[Instrument]:
        return list(self._instruments)

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [item for item in self._instruments if item.asset_class == asset_class]

    @staticmethod
    def _build_instruments(seed_path: Path) -> list[Instrument]:
        rows = load_universe_seed(seed_path)
        return [
            Instrument(
                symbol=row["symbol"],
                name=row["name"],
                asset_class=AssetClass(row["asset_class"]),
                currency=row["currency"],
            )
            for row in rows
        ]
