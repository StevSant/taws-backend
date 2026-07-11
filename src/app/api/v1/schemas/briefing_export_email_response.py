from pydantic import BaseModel


class BriefingExportEmailResponse(BaseModel):
    """Response payload for `POST /api/v1/briefings/{briefing_id}/export/email`.

    `delivered` is always `False` today: only `LoggingEmailSender` (a no-op/logging
    stand-in) is wired behind the `EmailSender` port — see that adapter's docstring
    for why a real SMTP/email-service integration is deferred rather than half-built.
    The composed email, with the rendered PDF attached, is logged server-side, not
    actually delivered to `recipient`.
    """

    recipient: str
    delivered: bool
    detail: str
