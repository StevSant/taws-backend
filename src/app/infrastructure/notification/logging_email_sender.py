import logging

from app.domain.notification.ports import EmailSender

logger = logging.getLogger(__name__)


class LoggingEmailSender(EmailSender):
    """No-op `EmailSender` adapter: logs the composed email instead of delivering it.

    Deliberate scope decision for issue #22: sending real email needs an SMTP/
    email-service integration (AWS SES, SendGrid, Resend, ...) with delivery
    credentials this codebase doesn't have configured, so building a working
    integration here would mean shipping unverifiable, untestable code. This adapter
    keeps the "trigger an email send" flow demo-able end to end (compose -> render PDF
    -> "deliver") without hard-depending on a real mail provider — same stand-in
    pattern as `LoggingNotificationChannel` for Watchdog alerts before issue #14's
    Telegram adapter landed. Swap this out in `Container.get_email_sender()` once a
    real provider is wired; nothing in `application/`/`api/` needs to change.
    """

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment: bytes | None = None,
        attachment_filename: str | None = None,
    ) -> None:
        logger.info(
            "email composed (not delivered — no email provider configured): to=%s "
            "subject=%r body_len=%d attachment=%s",
            to,
            subject,
            len(body),
            attachment_filename if attachment is not None else None,
        )
