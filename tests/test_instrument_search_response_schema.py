"""`InstrumentSearchResponse`: `GET /instruments/search`'s response is a plain
list of `CoinCandidateResponse` — a type alias, not a wrapper object, so the
frontend gets a bare JSON array (matching the instrument-search spec's shape).
"""

from app.api.v1.schemas import CoinCandidateResponse, InstrumentSearchResponse
from app.domain.market.entities import CoinCandidate


def test_instrument_search_response_is_a_list_of_coin_candidate_responses() -> None:
    candidates = [
        CoinCandidate(id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb=""),
        CoinCandidate(id="bitcoin", symbol="btc", name="Bitcoin", market_cap_rank=1, thumb=""),
    ]

    response: InstrumentSearchResponse = [
        CoinCandidateResponse.model_validate(candidate) for candidate in candidates
    ]

    assert len(response) == 2
    assert response[0].symbol == "doge"


def test_instrument_search_response_can_be_empty() -> None:
    response: InstrumentSearchResponse = []

    assert response == []
