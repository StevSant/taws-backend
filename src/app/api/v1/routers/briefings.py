from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_reasoning_llm_provider,
    get_resolve_locale_use_case,
    get_signal_repository,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.mappers import resolve_linked_signals
from app.api.v1.schemas import BriefingResponse, CurrentUser, GenerateBriefingRequest
from app.application.briefing import EmptyWatchlistError
from app.application.briefing.use_cases import GenerateBriefing
from app.application.compliance import ComplianceViolationError
from app.application.profile.use_cases import ResolveLocale
from app.domain.agents.ports import LLMProvider
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(prefix="/watchlists/{watchlist_id}/briefings", tags=["briefings"])


async def _require_owned_watchlist(
    watchlist_id: str, user: CurrentUser, watchlist_repository: WatchlistRepository
) -> None:
    """Raise 404 unless `watchlist_id` exists and belongs to `user`.

    Same ownership-check pattern as `_get_owned_watchlist` in `watchlists.py` (404, not
    403, even when the watchlist belongs to someone else, so this never confirms another
    user's watchlist id exists) — kept as a small local duplicate rather than importing
    that router's private helper across modules, since routers stay independent.
    """
    watchlist = await watchlist_repository.get(watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist not found")


async def _to_response(briefing: Briefing, signal_repository: SignalRepository) -> BriefingResponse:
    """Validate a domain `Briefing` and enrich its `linked_signal_ids` into `linked_signals`.

    Resolution runs here in the API layer (via the injected port), keeping the domain
    `Briefing` — which carries only the raw ids — unaware of the read-time enrichment.
    """
    response = BriefingResponse.model_validate(briefing)
    response.linked_signals = await resolve_linked_signals(
        briefing.linked_signal_ids, signal_repository
    )
    return response


@router.post("", status_code=status.HTTP_201_CREATED)
async def generate_briefing(
    watchlist_id: str,
    payload: GenerateBriefingRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
    # Reasoning tier (#28): composing a briefing synthesizes many signals across a watchlist
    # into one narrative — the Advisor's flagship analytical call.
    llm_provider: Annotated[LLMProvider, Depends(get_reasoning_llm_provider)],
    resolve_locale: Annotated[ResolveLocale, Depends(get_resolve_locale_use_case)],
) -> BriefingResponse:
    """Trigger the Advisor briefing pipeline on-demand for a watchlist (HU3).

    Button-style trigger; scheduling a recurring briefing is a separate T1 issue.

    The briefing is written in the locale `ResolveLocale` picks (issue #67): `payload.locale`
    when the UI sends one, else the owner's stored `preferred_locale`, else
    `Settings.default_locale`.
    """
    await _require_owned_watchlist(watchlist_id, user, watchlist_repository)
    use_case = GenerateBriefing(
        watchlist_repository=watchlist_repository,
        signal_repository=signal_repository,
        briefing_repository=briefing_repository,
        llm_provider=llm_provider,
    )
    locale = await resolve_locale.execute(user_id=user.id, requested_locale=payload.locale)
    try:
        briefing = await use_case.execute(watchlist_id, locale=locale)
    except EmptyWatchlistError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ComplianceViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return await _to_response(briefing, signal_repository)


@router.get("")
async def list_briefings(
    watchlist_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
) -> list[BriefingResponse]:
    """List every briefing generated for a watchlist owned by the authenticated user."""
    await _require_owned_watchlist(watchlist_id, user, watchlist_repository)
    briefings = await briefing_repository.list_for_watchlist(watchlist_id)
    return [await _to_response(briefing, signal_repository) for briefing in briefings]
