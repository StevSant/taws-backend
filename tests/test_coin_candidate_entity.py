"""`CoinCandidate`: a frozen DTO for one CoinGecko `/search` hit.

Round-trips the fields `SearchCoins`/`RegisterInstrument` need to resolve and
register a crypto instrument: CoinGecko's own `id`, ticker `symbol`, display
`name`, `market_cap_rank` (nullable — very small-cap coins have none), and a
`thumb` image URL for the frontend picker.
"""

from app.domain.market.entities import CoinCandidate


def test_coin_candidate_round_trips_all_fields() -> None:
    candidate = CoinCandidate(
        id="bitcoin",
        symbol="btc",
        name="Bitcoin",
        market_cap_rank=1,
        thumb="https://assets.coingecko.com/coins/images/1/thumb/bitcoin.png",
    )

    assert candidate.id == "bitcoin"
    assert candidate.symbol == "btc"
    assert candidate.name == "Bitcoin"
    assert candidate.market_cap_rank == 1
    assert candidate.thumb == "https://assets.coingecko.com/coins/images/1/thumb/bitcoin.png"


def test_coin_candidate_market_cap_rank_is_nullable() -> None:
    candidate = CoinCandidate(
        id="some-micro-cap",
        symbol="mic",
        name="Some Micro Cap",
        market_cap_rank=None,
        thumb="",
    )

    assert candidate.market_cap_rank is None
