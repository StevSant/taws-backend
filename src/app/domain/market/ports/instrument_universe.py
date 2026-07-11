from abc import ABC, abstractmethod

from app.domain.market.entities import AssetClass, Instrument


class InstrumentUniverse(ABC):
    """Port for the curated, config-driven set of instruments the product tracks.

    Adapter: `JsonInstrumentUniverse`, loaded from the packaged `universe.json`
    seed and cached at load — this port is synchronous since the universe is a
    small, in-memory, already-loaded set.
    """

    @abstractmethod
    def all(self) -> list[Instrument]:
        """Return every instrument in the universe."""
        raise NotImplementedError

    @abstractmethod
    def by_symbol(self, symbol: str) -> Instrument | None:
        """Return the instrument with the given symbol (case-insensitive), if any."""
        raise NotImplementedError

    @abstractmethod
    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        """Return every instrument belonging to the given asset class."""
        raise NotImplementedError
