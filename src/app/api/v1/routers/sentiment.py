from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import get_analyze_sentiment_use_case
from app.api.v1.schemas import SentimentReadingResponse
from app.application.sentiment.unknown_instrument_error import UnknownInstrumentError
from app.application.sentiment.use_cases import AnalyzeSentiment

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


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
