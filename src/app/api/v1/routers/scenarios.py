from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_preset_scenario_rows,
    get_scenario_repository,
    get_scenario_simulation_runner,
    require_current_user,
)
from app.api.v1.schemas import (
    CurrentUser,
    GenerateScenarioRequest,
    ScenarioMonitorResponse,
    ScenarioPresetResponse,
    ScenarioResultResponse,
)
from app.application.compliance import ComplianceViolationError
from app.application.scenario import InvalidScenarioIntakeError, UnknownPresetError
from app.application.scenario.use_cases import ArmScenarioMonitor
from app.core.config import Settings, get_settings
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
    scenario_simulation_runner: Annotated[
        ScenarioSimulationRunner, Depends(get_scenario_simulation_runner)
    ],
) -> ScenarioResultResponse:
    """Run the Scenario Simulation graph end to end (issue #12) — Intake -> Context
    gathering -> Causal chain -> Quantification -> Synthesis -> Compliance — for either a
    curated preset id or free-form text, and return the persisted `ScenarioResult`.

    Not user-scoped (no `require_current_user`): a scenario run is shared/global research,
    not per-user data — same visibility model as `POST /api/v1/signals/generate`. See
    `ScenarioRepository`'s docstring for the full ownership rationale.
    """
    try:
        result = await scenario_simulation_runner.execute(
            preset_id=payload.preset_id, free_text=payload.free_text
        )
    except InvalidScenarioIntakeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnknownPresetError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ComplianceViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ScenarioResultResponse.model_validate(result)


@router.get("")
async def list_recent_scenarios(
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
    limit: Annotated[int, Query(ge=1, le=_MAX_RECENT_LIMIT)] = _DEFAULT_RECENT_LIMIT,
) -> list[ScenarioResultResponse]:
    """List the most recently generated scenario results, most-recent first."""
    results = await scenario_repository.list_recent(limit)
    return [ScenarioResultResponse.model_validate(result) for result in results]


@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: str,
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
) -> ScenarioResultResponse:
    """Retrieve a single persisted scenario result by id."""
    result = await scenario_repository.get(scenario_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    return ScenarioResultResponse.model_validate(result)


@router.post("/{scenario_id}/arm", status_code=status.HTTP_201_CREATED)
async def arm_scenario_monitor(
    scenario_id: str,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    scenario_repository: Annotated[ScenarioRepository, Depends(get_scenario_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioMonitorResponse:
    """ "Arm monitor" action on a saved `ScenarioResult` (issue #18) — turns it into a
    standing Watchdog rule that pings the requesting user over Telegram if the scenario
    looks like it's materializing. Authenticated (unlike scenario generation itself):
    arming ties to a specific user for delivery, see `ScenarioMonitor`'s docstring.

    Idempotent per `(scenario_id, user_id)` — re-arming (including re-arming a `matched`
    or `expired` monitor) resets it back to `armed` with a fresh window; see
    `ArmScenarioMonitor`.
    """
    use_case = ArmScenarioMonitor(
        scenario_repository=scenario_repository, ttl_days=settings.scenario_monitor_ttl_days
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
