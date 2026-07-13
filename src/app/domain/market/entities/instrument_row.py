from dataclasses import dataclass

from app.domain.market.entities.asset_class import AssetClass


@dataclass(frozen=True, slots=True)
class InstrumentRow:
    """A raw `public.instruments` catalog row, including vendor-id overrides.

    Distinct from the pure `Instrument` entity: `coingecko_id`/`yfinance_symbol`
    MUST NOT leak into `Instrument` (see the instrument-catalog spec's "vendor ids
    do not leak into the domain entity" scenario). This DTO exists so
    `SupabaseInstrumentCatalogRepository`/`SupabaseInstrumentUniverse` and
    `get_market_data_provider`'s override-map building have a typed shape for the
    raw row, instead of passing dicts around.
    """

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    coingecko_id: str | None = None
    yfinance_symbol: str | None = None
