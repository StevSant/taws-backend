import logging

from app.application.instruments.errors import SymbolCollisionError
from app.application.instruments.register_instrument_result import RegisterInstrumentResult
from app.domain.market.entities import AssetClass, CoinCandidate, Instrument, InstrumentRow
from app.domain.market.ports import (
    InstrumentCatalogRepository,
    InstrumentUniverse,
    MutableInstrumentUniverse,
)
from app.domain.watchlist.ports import WatchlistRepository

logger = logging.getLogger(__name__)


class RegisterInstrument:
    """Turn a resolved CoinGecko candidate into a persisted, globally-visible
    instrument AND add it to the caller's watchlist, in one action.

    Order (design's FIX #5, exact and safe to interrupt at any step after the
    first): 1) read-only collision check, 2) idempotent catalog upsert (the
    durable step — MUST succeed first), 3) append to the in-memory universe
    (`MutableInstrumentUniverse.add`, no-op if already present), 4) add to the
    caller's watchlist (idempotent, per-user). If step 4 fails after 2+3
    succeed, the instrument is already real and globally visible — this method
    returns `watchlisted=False` instead of raising, so the router can respond
    502 without rolling back the catalog write (no corruption, no dangling
    partial success).
    """

    def __init__(
        self,
        catalog_repository: InstrumentCatalogRepository,
        universe: InstrumentUniverse,
        watchlist_repository: WatchlistRepository,
    ) -> None:
        self._catalog_repository = catalog_repository
        self._universe = universe
        self._watchlist_repository = watchlist_repository

    async def execute(
        self, candidate: CoinCandidate, watchlist_id: str
    ) -> RegisterInstrumentResult:
        symbol = candidate.symbol.upper()

        existing = self._universe.by_symbol(symbol)
        if existing is not None and existing.asset_class is not AssetClass.CRYPTO:
            raise SymbolCollisionError(symbol=symbol, existing_instrument=existing)

        row = InstrumentRow(
            symbol=symbol,
            name=candidate.name,
            asset_class=AssetClass.CRYPTO,
            currency="USD",
            coingecko_id=candidate.id,
        )
        await self._catalog_repository.upsert(row)

        instrument = Instrument(
            symbol=symbol, name=row.name, asset_class=AssetClass.CRYPTO, currency=row.currency
        )
        mutable_universe: MutableInstrumentUniverse = self._universe  # type: ignore[assignment]
        # `add_row(row)`, not `add(instrument)` (CRITICAL fix, post-hoc adversarial
        # review): `row` carries `coingecko_id=candidate.id`, which `add()` would
        # silently drop by rebuilding a vendor-id-less `InstrumentRow` — leaving the
        # new coin's price unresolvable via CoinGecko until process restart.
        mutable_universe.add_row(row)

        watchlisted = await self._add_to_watchlist(watchlist_id, symbol)
        return RegisterInstrumentResult(instrument=instrument, watchlisted=watchlisted)

    async def _add_to_watchlist(self, watchlist_id: str, symbol: str) -> bool:
        try:
            await self._watchlist_repository.add_item(watchlist_id, symbol)
        except Exception:
            logger.warning(
                "Watchlist add failed after catalog upsert for %s; instrument is "
                "persisted and globally visible, watchlist add can be retried.",
                symbol,
                exc_info=True,
            )
            return False
        return True
