from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    """CoinGecko `/coins/markets`-sourced enrichment fields for one instrument.

    Every field is nullable: `InstrumentMetadataProvider.get_metadata_batch` omits
    symbols it couldn't resolve (missing CoinGecko mapping, rate-limited, or the
    provider is fully down), and `ListEnrichedInstruments` maps that absence onto
    an `InstrumentMetadata` whose fields are all `None` — same graceful-degradation
    contract as `EnrichedInstrument`'s existing market-derived fields.
    """

    market_cap: float | None
    volume_24h: float | None
    change_7d_pct: float | None
