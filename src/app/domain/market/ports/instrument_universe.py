from abc import ABC, abstractmethod

from app.domain.market.entities import AssetClass, Instrument


class InstrumentUniverse(ABC):
    """Port for the curated, DB-backed set of instruments the product tracks.

    Adapter: `SupabaseInstrumentUniverse`, loaded once from the global
    `public.instruments` table via an async `create()` factory (awaited at app
    startup) and cached as an in-memory index — this port stays synchronous since,
    once loaded, the universe is a small, already-loaded, in-memory set.
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
