from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoinCandidate:
    """One ranked hit from CoinGecko's `/search` endpoint.

    Pure DTO — no vendor SDK types leak past this. `market_cap_rank` is nullable:
    CoinGecko omits it for very small-cap/unranked coins. `RegisterInstrument`
    (Slice 2) turns a chosen candidate into a persisted `InstrumentRow` with
    `coingecko_id=id` and `asset_class=CRYPTO`.
    """

    id: str
    symbol: str
    name: str
    market_cap_rank: int | None
    thumb: str
