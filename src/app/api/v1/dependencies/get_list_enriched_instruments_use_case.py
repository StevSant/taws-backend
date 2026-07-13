from typing import Annotated

from fastapi import Depends

from app.application.instruments.use_cases import ListEnrichedInstruments
from app.core.di import Container, get_container


def get_list_enriched_instruments_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> ListEnrichedInstruments:
    """FastAPI dependency resolving the enriched-universe listing use case.

    Delegates to `Container.get_list_enriched_instruments_use_case()` — the single
    construction site shared with the chat agents' `get_market_movers` tool — instead of
    assembling the pipeline from its ports here, so the REST endpoint and the agent tool
    can never drift apart.
    """
    return container.get_list_enriched_instruments_use_case()
