from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.language_models import BaseChatModel

from app.api.v1.dependencies import (
    get_chat_model,
    get_instrument_universe,
    get_market_data_provider,
    get_news_provider,
    get_signal_repository,
)
from app.api.v1.schemas import GenerateSignalRequest, SignalResponse
from app.application.signals import InsufficientEvidenceError, UnknownInstrumentError
from app.application.signals.use_cases import GenerateSignal
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
    model: Annotated[BaseChatModel, Depends(get_chat_model)],
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
        model=model,
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
