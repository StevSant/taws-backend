from abc import ABC, abstractmethod

from app.domain.market.entities import InstrumentRow


class InstrumentCatalogRepository(ABC):
    """Port for the persisted, global instrument catalog (`public.instruments`).

    Adapter: `SupabaseInstrumentCatalogRepository`. Consumed by
    `SupabaseInstrumentUniverse.create()` (bulk load) and, in Slice 2, by
    `RegisterInstrument` (single-row upsert on user registration).
    """

    @abstractmethod
    async def upsert(self, row: InstrumentRow) -> None:
        """Insert or update one catalog row, keyed by `symbol` (idempotent)."""
        raise NotImplementedError

    @abstractmethod
    async def all_rows(self) -> list[InstrumentRow]:
        """Return every row currently in the catalog."""
        raise NotImplementedError
