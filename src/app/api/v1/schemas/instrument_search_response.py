from app.api.v1.schemas.coin_candidate_response import CoinCandidateResponse

# `GET /api/v1/instruments/search` returns a bare JSON array (never a wrapper
# object), matching the instrument-search spec's "ranked list of candidates"
# shape — a type alias, not a Pydantic RootModel (see the `fastapi` skill's
# "do not use Pydantic RootModels" guidance).
InstrumentSearchResponse = list[CoinCandidateResponse]
