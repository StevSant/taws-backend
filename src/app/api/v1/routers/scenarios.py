import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_notification_channel,
    get_preset_scenario_rows,
    get_scenario_repository,
    get_scenario_simulation_runner,
    require_current_user,
)
from app.api.v1.schemas import (
    CurrentUser,
    GenerateScenarioRequest,
    ScenarioMonitorResponse,
    ScenarioMonitorStatusResponse,
    ScenarioPresetResponse,
    ScenarioResultResponse,
)
from app.application.compliance import ComplianceViolationError
from app.application.scenario import (
    InvalidScenarioIntakeError,
    ScenarioOutOfScopeError,
    ScenarioSynthesisUnavailableError,
    UnknownPresetError,
    scenario_unavailable_message,
)
from app.application.scenario.use_cases import ArmScenarioMonitor
from app.core.config import Settings, get_settings
from app.domain.notification.ports import NotificationChannel
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.agents.scenario import ScenarioSimulationRunner

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

_DEFAULT_RECENT_LIMIT = 20
_MAX_RECENT_LIMIT = 100


@router.get("/presets")
async def list_scenario_presets(
    preset_rows: Annotated[list[dict[str, Any]], Depends(get_preset_scenario_rows)],
) -> list[ScenarioPresetResponse]:
    """List the curated preset "what-if" scenarios (issue #12), for a Scenario Lab preset
    picker. Registered before `GET /{scenario_id}` so this static path isn't shadowed by
    that dynamic one.
    """
    return [ScenarioPresetResponse.model_validate(row) for row in preset_rows]


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_scenario(
    payload: GenerateScenarioRequest,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_simulation_runner: Annotated[
        ScenarioSimulationRunner, Depends(get_scenario_simulation_runner)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioResultResponse:
    """Run the Scenario Simulation graph end to end (issue #12) — Intake -> Context
    gathering -> Causal chain -> Quantification -> Synthesis -> Compliance — for either a
    curated preset id or free-form text, and return the persisted `ScenarioResult`.

    Authenticated: previously anonymous, which left a public URL fanning out to a six-node
    LLM pipeline on every call. Auth also gives us the author to scope by — a PRESET run is
    still global/shared research (`author_id` stays null), but a FREE-FORM run is stamped
    with `current_user.id` so the user's own typed "what if" stays private to them (migration
    0025) instead of appearing in everyone's "Mis escenarios".
    """
    locale = payload.locale or settings.default_locale
    try:
        result = await scenario_simulation_runner.execute(
            preset_id=payload.preset_id,
            free_text=payload.free_text,
            locale=locale,
            user_id=current_user.id,
        )
    except InvalidScenarioIntakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ScenarioOutOfScopeError as exc:
        # The prompt has no market/financial dimension (e.g. a personal/relationship "what
        # if"). Refuse with the model's localized reason instead of fabricating an analysis.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnknownPresetError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScenarioSynthesisUnavailableError as exc:
        # Synthesis couldn't produce a real analysis after retries (issue #64): surface an
        # honest, localized "unavailable" state instead of a fabricated zero-confidence
        # result. The real cause is already logged server-side by the use case.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=scenario_unavailable_message(locale),
        ) from exc
    except ComplianceViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ScenarioResultResponse.model_validate(result)


@router.get("")
async def list_recent_scenarios(
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
    limit: Annotated[int, Query(ge=1, le=_MAX_RECENT_LIMIT)] = _DEFAULT_RECENT_LIMIT,
) -> list[ScenarioResultResponse]:
    """List the scenario results visible to the caller, most-recent first: every global/
    shared run plus this user's own free-form runs. Scoped so one user's private "what if"
    never surfaces in another's history (migration 0025)."""
    results = await scenario_repository.list_recent(current_user.id, limit)
    return [ScenarioResultResponse.model_validate(result) for result in results]


@router.get("/monitors")
async def list_scenario_monitors(
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
) -> list[ScenarioMonitorStatusResponse]:
    """List the caller's armed Scenario Monitors with their live status (issue #18 / C3).

    Backs the frontend's in-app notification poller, which diffs this on an interval to raise
    an `ARMED`->`MATCHED` breach in the notification bell (the matching + Telegram delivery
    already run server-side via `EvaluateScenarioMonitors`). Reuses the repository's existing
    reads — `list_monitors_for_user` for the rows, `get` for each row's scenario `title` —
    rather than adding a use-case pipeline. Registered before `GET /{scenario_id}` so this
    static path isn't shadowed by that dynamic one, same guard `GET /presets` uses.
    """
    monitors = await scenario_repository.list_monitors_for_user(current_user.id)
    scenarios = await asyncio.gather(
        *(scenario_repository.get(monitor.scenario_id) for monitor in monitors)
    )
    return [
        ScenarioMonitorStatusResponse(
            scenario_id=monitor.scenario_id,
            title=scenario.title if scenario is not None else "",
            status=monitor.status,
            armed_at=monitor.armed_at,
            matched_at=monitor.matched_at,
            match_reason=monitor.match_reason,
        )
        for monitor, scenario in zip(monitors, scenarios, strict=True)
    ]


@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: str,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
) -> ScenarioResultResponse:
    """Retrieve a single persisted scenario result by id.

    A free-form run is private to its author: 404 (not 403) for anyone else, so the endpoint
    doesn't even leak that the id exists. Global runs (`author_id is null`) are readable by
    any authenticated user, same as before."""
    result = await scenario_repository.get(scenario_id)
    if result is None or (result.author_id is not None and result.author_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return ScenarioResultResponse.model_validate(result)


@router.post("/{scenario_id}/arm", status_code=status.HTTP_201_CREATED)
async def arm_scenario_monitor(
    scenario_id: str,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
    notification_channel: Annotated[NotificationChannel, Depends(get_notification_channel)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioMonitorResponse:
    """ "Arm monitor" action on a saved `ScenarioResult` (issue #18) — turns it into a
    standing Watchdog rule that pings the requesting user over Telegram if the scenario
    looks like it's materializing, and sends an immediate confirmation that the watch is on.

    Idempotent per `(scenario_id, user_id)` — re-arming (including re-arming a `matched`
    or `expired` monitor) resets it back to `armed` with a fresh window; see
    `ArmScenarioMonitor`.
    """
    use_case = ArmScenarioMonitor(
        scenario_repository=scenario_repository,
        ttl_days=settings.scenario_monitor_ttl_days,
        notification_channel=notification_channel,
        frontend_base_url=settings.frontend_base_url,
    )
    monitor = await use_case.execute(scenario_id=scenario_id, user_id=current_user.id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return ScenarioMonitorResponse.model_validate(monitor)


@router.delete("/{scenario_id}/arm", status_code=status.HTTP_204_NO_CONTENT)
async def disarm_scenario_monitor(
    scenario_id: str,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
) -> None:
    """Disarm the requesting user's monitor for this scenario, if any. Idempotent — no-op
    (still `204`) if the user never armed this scenario or already disarmed it."""
    await scenario_repository.disarm_monitor(scenario_id=scenario_id, user_id=current_user.id)
