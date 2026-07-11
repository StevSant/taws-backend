from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingDocumentRenderer
from app.domain.notification.ports import EmailSender

_EMAIL_SUBJECT_TEMPLATE = "TAWS Briefing — watchlist {watchlist_id}"
_ATTACHMENT_FILENAME_TEMPLATE = "briefing-{briefing_id}.pdf"


class ExportBriefingDocument:
    """Briefing export pipeline (issue #22): a persisted `Briefing` -> a PDF, either
    returned directly for download (`render_pdf`) or attached to an email
    (`send_by_email`). Both paths render through the same `BriefingDocumentRenderer`
    port, so the PDF a user downloads and the PDF a user gets emailed are always
    byte-for-byte the same document.

    `send_by_email` depends on `EmailSender`, which currently has exactly one
    adapter — `LoggingEmailSender`, a no-op/logging stand-in (see that adapter's
    docstring for why a real SMTP/email-service integration is deferred). Calling
    `send_by_email` today logs the composed email instead of delivering it; this use
    case doesn't know or care which adapter is behind the port, same as every other
    port-based use case in this codebase.
    """

    def __init__(
        self, document_renderer: BriefingDocumentRenderer, email_sender: EmailSender
    ) -> None:
        self._document_renderer = document_renderer
        self._email_sender = email_sender

    def render_pdf(self, briefing: Briefing) -> bytes:
        """Render `briefing` to PDF bytes, ready to stream back as a download."""
        return self._document_renderer.render(briefing)

    async def send_by_email(self, briefing: Briefing, recipient: str) -> None:
        """Render `briefing` to PDF and hand it to the configured `EmailSender` as an
        attachment for `recipient`."""
        pdf_bytes = self._document_renderer.render(briefing)
        await self._email_sender.send(
            to=recipient,
            subject=_EMAIL_SUBJECT_TEMPLATE.format(watchlist_id=briefing.watchlist_id),
            body=briefing.summary,
            attachment=pdf_bytes,
            attachment_filename=_ATTACHMENT_FILENAME_TEMPLATE.format(briefing_id=briefing.id),
        )
