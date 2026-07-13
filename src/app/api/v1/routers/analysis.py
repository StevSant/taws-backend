from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import get_refresh_tracked_analysis_use_case
from app.api.v1.schemas import RefreshAnalysisResponse
from app.application.analysis.use_cases import RefreshTrackedAnalysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_tracked_analysis(
    use_case: Annotated[RefreshTrackedAnalysis, Depends(get_refresh_tracked_analysis_use_case)],
) -> RefreshAnalysisResponse:
    """Refresh shared analysis for every watchlisted instrument right now (issue #29).

    Runs the SAME `RefreshTrackedAnalysis` use case the scheduler's periodic tick calls (see
    `infrastructure/scheduling`), so a manual refresh behaves identically to a scheduled one —
    the "on-demand endpoint runs the exact scheduled-job use case" pattern
    `POST /api/v1/watchdog/scan` established.

    This is a "don't wait for the next tick" trigger, not a cache-buster: it honors the
    freshness gate (`force=False`), so instruments whose analysis is still within its TTL cost
    nothing. There is intentionally no way to force a full recompute from an unauthenticated
    endpoint — see `GenerateSignal.execute`'s docstring.

    Not user-scoped (a global pass across every watchlist), same visibility model as
    `POST /api/v1/signals/generate`.
    """
    result = await use_case.execute()
    return RefreshAnalysisResponse.model_validate(result)
