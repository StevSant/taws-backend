from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.briefing.ports import BriefingDocumentRenderer


def get_briefing_document_renderer(
    container: Annotated[Container, Depends(get_container)],
) -> BriefingDocumentRenderer:
    """FastAPI dependency resolving the configured BriefingDocumentRenderer from the DI
    container."""
    return container.get_briefing_document_renderer()
