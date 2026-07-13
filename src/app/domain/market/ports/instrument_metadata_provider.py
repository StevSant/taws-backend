from abc import ABC, abstractmethod

from app.domain.market.entities import InstrumentMetadata


class InstrumentMetadataProvider(ABC):
    """Port for batch-fetching CoinGecko market-metadata enrichment fields.

    Deliberately a NEW, dedicated port — NOT an extension of `MarketDataProvider`
    (design decision #2): `MarketDataProvider` feeds the asset-class-agnostic
    `RoutingMarketDataProvider` and only exposes `get_price_series`/
    `get_last_price`, whereas `/coins/markets` is crypto-only and must
    null-degrade in isolation. Adapter: `infrastructure/marketdata/
    coingecko_instrument_metadata_provider.py` (ONE batch `/coins/markets?ids=`
    call per invocation), reusing the shared cooldown/circuit-breaker pattern.
    """

    @abstractmethod
    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        """Return metadata for as many `symbols` as could be resolved.

        Missing/failed symbols are simply OMITTED from the returned dict — the
        caller (`ListEnrichedInstruments`) maps an absent key onto `None` fields,
        never a crash or a dropped row. A fully unavailable CoinGecko returns an
        empty dict, not an exception.
        """
        raise NotImplementedError
