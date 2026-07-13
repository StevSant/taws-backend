from pydantic import BaseModel, Field

_SYMBOL_PATTERN = r"^[A-Za-z0-9.\-]{1,20}$"
_COINGECKO_ID_PATTERN = r"^[a-z0-9\-]{1,80}$"


class RegisterInstrumentRequest(BaseModel):
    """Request payload for `POST /api/v1/instruments` — a resolved CoinGecko candidate.

    Field patterns (MEDIUM fix, post-hoc adversarial review): ANY authenticated
    user can trigger this endpoint's service-role (RLS-bypassing) global-catalog
    write, so `symbol`/`coingecko_id` are bounded to CoinGecko's own actual id/
    ticker character sets instead of accepting arbitrary junk (e.g. `<script>`,
    embedded whitespace, or oversized strings).
    """

    coingecko_id: str = Field(..., pattern=_COINGECKO_ID_PATTERN)
    symbol: str = Field(..., pattern=_SYMBOL_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)
