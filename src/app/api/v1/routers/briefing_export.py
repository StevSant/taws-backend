from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.v1.dependencies import (
    get_briefing_document_renderer,
    get_briefing_repository,
    get_email_sender,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.schemas import BriefingExportEmailRequest, BriefingExportEmailResponse, CurrentUser
from app.application.briefing.use_cases import ExportBriefingDocument
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingDocumentRenderer, BriefingRepository
from app.domain.notification.ports import EmailSender
from app.domain.watchlist.ports import WatchlistRepository

router = APIRouter(prefix="/briefings", tags=["briefings"])


async def _get_owned_briefing(
    briefing_id: str,
    user: CurrentUser,
    briefing_repository: BriefingRepository,
    watchlist_repository: WatchlistRepository,
) -> Briefing:
    """Return the briefing if it exists and its watchlist belongs to `user`, else raise 404.

    Same ownership check as `reviews.py`'s `_get_owned_briefing` — kept as a small
    local duplicate rather than a cross-module import, since routers stay independent
    (see that function's docstring for the full rationale, including why this is 404
    rather than 403 either way).
    """
    briefing = await briefing_repository.get(briefing_id)
    if briefing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    watchlist = await watchlist_repository.get(briefing.watchlist_id)
    if watchlist is None or watchlist.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    return briefing


@router.get("/{briefing_id}/export.pdf")
async def export_briefing_pdf(
    briefing_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    document_renderer: Annotated[BriefingDocumentRenderer, Depends(get_briefing_document_renderer)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> Response:
    """Download a briefing as a PDF (issue #22).

    Renders the same fuller document structure issue #16 added to `Briefing`:
    executive summary, per-instrument breakdown, open review items, and the
    disclaimer footer — see `BriefingDocumentRenderer`'s docstring. Ownership-scoped
    via `_get_owned_briefing`, same 404-either-way contract as the review endpoints.

    `email_sender` is DI-resolved (a cached, cheap-to-construct singleton) purely so
    `ExportBriefingDocument` is built the same way on every path — this endpoint's
    `render_pdf` call never invokes it.
    """
    briefing = await _get_owned_briefing(
        briefing_id, user, briefing_repository, watchlist_repository
    )
    use_case = ExportBriefingDocument(
        document_renderer=document_renderer, email_sender=email_sender
    )
    pdf_bytes = use_case.render_pdf(briefing)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="briefing-{briefing.id}.pdf"',
        },
    )


@router.post("/{briefing_id}/export/email", status_code=status.HTTP_202_ACCEPTED)
async def export_briefing_by_email(
    briefing_id: str,
    payload: BriefingExportEmailRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    briefing_repository: Annotated[BriefingRepository, Depends(get_briefing_repository)],
    watchlist_repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    document_renderer: Annotated[BriefingDocumentRenderer, Depends(get_briefing_document_renderer)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> BriefingExportEmailResponse:
    """Trigger an email send of a briefing's PDF (issue #22's "and/or trigger an email
    send" acceptance criterion).

    Renders the same PDF `export_briefing_pdf` returns and hands it to the configured
    `EmailSender`. Today that's always `LoggingEmailSender` — a no-op/logging
    stand-in, since no real SMTP/email-service integration is configured in this
    codebase (see that adapter's docstring). The response's `delivered: false` makes
    that explicit to the caller rather than implying a real email went out.
    """
    briefing = await _get_owned_briefing(
        briefing_id, user, briefing_repository, watchlist_repository
    )
    use_case = ExportBriefingDocument(
        document_renderer=document_renderer, email_sender=email_sender
    )
    await use_case.send_by_email(briefing, recipient=payload.to)
    return BriefingExportEmailResponse(
        recipient=payload.to,
        delivered=False,
        detail=(
            "No email provider is configured in this environment; the composed "
            "email (with the PDF attached) was logged, not delivered."
        ),
    )
