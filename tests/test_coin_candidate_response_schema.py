"""`CoinCandidateResponse`: response payload for one `GET /instruments/search` hit."""

from app.api.v1.schemas import CoinCandidateResponse
from app.domain.market.entities import CoinCandidate


def test_coin_candidate_response_matches_coin_candidate_fields() -> None:
    candidate = CoinCandidate(
        id="dogecoin",
        symbol="doge",
        name="Dogecoin",
        market_cap_rank=10,
        thumb="https://assets.coingecko.com/coins/images/5/thumb/dogecoin.png",
    )

    response = CoinCandidateResponse.model_validate(candidate)

    assert response.id == "dogecoin"
    assert response.symbol == "doge"
    assert response.name == "Dogecoin"
    assert response.market_cap_rank == 10
    assert response.thumb == "https://assets.coingecko.com/coins/images/5/thumb/dogecoin.png"


def test_coin_candidate_response_allows_null_market_cap_rank() -> None:
    candidate = CoinCandidate(
        id="micro", symbol="mic", name="Micro", market_cap_rank=None, thumb=""
    )

    response = CoinCandidateResponse.model_validate(candidate)

    assert response.market_cap_rank is None
