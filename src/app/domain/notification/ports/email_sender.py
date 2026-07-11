from abc import ABC, abstractmethod


class EmailSender(ABC):
    """Port for sending an email, optionally with one binary attachment.

    Backs the briefing export feature's "and/or trigger an email send" acceptance
    criterion (issue #22) — `ExportBriefingDocument.send_by_email` renders a
    `Briefing` to PDF via `BriefingDocumentRenderer` and hands the bytes to this port
    as `attachment`.

    Issue #22 ships exactly one adapter — `LoggingEmailSender`
    (`infrastructure/notification/logging_email_sender.py`), a no-op/logging
    stand-in, same "unconfigured integration degrades gracefully" pattern as
    `LoggingNotificationChannel`. A real adapter (SMTP, AWS SES, SendGrid, Resend,
    ...) needs delivery credentials this codebase doesn't have configured yet, so it
    is deliberately deferred rather than half-built — see `Container.get_email_sender`
    for the wiring point a future adapter would replace.
    """

    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment: bytes | None = None,
        attachment_filename: str | None = None,
    ) -> None:
        """Send an email to `to`. `attachment`/`attachment_filename` are both set or
        both `None` — never one without the other. Must not raise for expected
        delivery failures — adapters should log/swallow those, same never-raise
        contract as `NotificationChannel.send`, so a bad delivery never crashes the
        caller."""
        raise NotImplementedError
