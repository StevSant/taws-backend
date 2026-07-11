from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    get_embedding_provider,
    get_instrument_universe,
    get_llm_provider,
    get_market_data_provider,
    get_news_provider,
    get_signal_repository,
    get_vector_store,
)
from app.api.v1.schemas import GenerateSignalRequest, SignalResponse
from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.signals import InsufficientEvidenceError, UnknownInstrumentError
from app.application.signals.use_cases import GenerateSignal
from app.core.config import Settings, get_settings
from app.domain.agents.ports import EmbeddingProvider, LLMProvider, VectorStore
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider, NewsProvider
from app.domain.signals.ports import SignalRepository

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_signal(
    payload: GenerateSignalRequest,
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SignalResponse:
    """Trigger the Analyst pipeline on-demand for one instrument (HU1/HU2).

    Not user-scoped (no `require_current_user`): a `Signal` is an Analyst-produced market
    observation about an instrument, not per-user data — same visibility model as
    `GET /api/v1/news` and `GET /api/v1/instruments`.
    """
    use_case = GenerateSignal(
        news_provider=news_provider,
        market_data_provider=market_data_provider,
        instrument_universe=instrument_universe,
        signal_repository=signal_repository,
        llm_provider=llm_provider,
        find_historical_analogs=FindHistoricalAnalogs(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            top_k=settings.historical_analogs_top_k,
        ),
        index_signal_analog=IndexSignalAnalog(
            embedding_provider=embedding_provider, vector_store=vector_store
        ),
    )
    try:
        signal = await use_case.execute(payload.instrument_symbol.upper())
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InsufficientEvidenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return SignalResponse.model_validate(signal)
