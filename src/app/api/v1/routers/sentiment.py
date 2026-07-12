from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    get_analyze_sentiment_use_case,
    get_fear_greed_provider,
    get_market_pulse_use_case,
)
from app.api.v1.schemas import FearGreedReadingResponse, MarketPulseResponse, SentimentReadingResponse
from app.application.sentiment.unknown_instrument_error import UnknownInstrumentError
from app.application.sentiment.use_cases import AnalyzeSentiment
from app.application.sentiment.use_cases.get_market_pulse import GetMarketPulse
from app.domain.sentiment.ports import FearGreedProvider

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/market-pulse")
async def get_market_pulse(
    use_case: Annotated[GetMarketPulse, Depends(get_market_pulse_use_case)],
) -> MarketPulseResponse:
    """Stock-market Fear & Greed (CNN) plus major index quotes for the Radar home panel."""
    snapshot = await use_case.execute()
    return MarketPulseResponse.model_validate(
        {
            "value": snapshot.fear_greed.value,
            "classification": snapshot.fear_greed.classification,
            "as_of": snapshot.fear_greed.as_of,
            "delta_points": snapshot.delta_points,
            "market": snapshot.market,
            "source": snapshot.source,
            "indices": snapshot.indices,
        }
    )


@router.get("/fear-greed")
async def get_fear_greed_index(
    fear_greed_provider: Annotated[FearGreedProvider, Depends(get_fear_greed_provider)],
) -> FearGreedReadingResponse:
    """Return the current market-wide Crypto Fear & Greed Index (alternative.me).

    Public, not user-scoped — same visibility model as `GET /api/v1/macro`. Used by
    the Radar macro panel and chat context rail for a quick sentiment read.
    """
    reading = await fear_greed_provider.get_fear_greed_index()
    return FearGreedReadingResponse.model_validate(reading)


@router.post("/{symbol}/analyze", status_code=status.HTTP_201_CREATED)
async def analyze_sentiment(
    symbol: str,
    use_case: Annotated[AnalyzeSentiment, Depends(get_analyze_sentiment_use_case)],
) -> SentimentReadingResponse:
    """Trigger the Sentiment Analyst on-demand for one instrument (issue #21): a news-tone
    score grounded in real recent news, plus the current market-wide Fear & Greed Index
    reading.

    Not user-scoped (no `require_current_user`) — a sentiment reading is research output
    about an instrument, not per-user data, same visibility model as
    `POST /api/v1/consequence-chains/generate`. Never persisted. Raises `404` for a symbol
    outside the curated universe (`UnknownInstrumentError`) — everything else about this
    pipeline degrades gracefully instead of raising (see `AnalyzeSentiment`'s docstring).
    """
    try:
        reading = await use_case.execute(symbol.upper())
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SentimentReadingResponse.model_validate(reading)
