from dataclasses import dataclass

from app.domain.market.entities import Instrument


@dataclass(frozen=True, slots=True)
class RegisterInstrumentResult:
    """Outcome of `RegisterInstrument.execute()` — always carries the persisted
    instrument; `watchlisted` is `False` only when the catalog/universe writes
    succeeded but the subsequent watchlist add failed (FIX #5 partial-failure
    semantics). The router maps `watchlisted=False` to HTTP 502.
    """

    instrument: Instrument
    watchlisted: bool
