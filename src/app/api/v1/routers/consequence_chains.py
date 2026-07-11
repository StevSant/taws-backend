from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import get_generate_consequence_chain_use_case
from app.api.v1.schemas import ConsequenceChainResponse, GenerateConsequenceChainRequest
from app.application.consequence.use_cases import GenerateConsequenceChain

router = APIRouter(prefix="/consequence-chains", tags=["consequence-chains"])


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_consequence_chain(
    payload: GenerateConsequenceChainRequest,
    use_case: Annotated[GenerateConsequenceChain, Depends(get_generate_consequence_chain_use_case)],
) -> ConsequenceChainResponse:
    """Trigger the Consequence Chain Analyst on-demand for one event/instrument (issue #8).

    Not user-scoped (no `require_current_user`): a causal chain is research output about
    an event/instrument, not per-user data — same visibility model as
    `POST /api/v1/signals/generate`. Never persisted, and never raises: `GenerateConsequenceChain`
    degrades to a fallback chain instead of erroring when structured output is unavailable
    (e.g. no API key), so this endpoint always returns `201`.

    This is the same `execute(subject)` use case the future Scenario Simulation graph
    (issue #12) is expected to call directly for its "Causal chain" step.
    """
    chain = await use_case.execute(payload.subject)
    return ConsequenceChainResponse.model_validate(chain)
