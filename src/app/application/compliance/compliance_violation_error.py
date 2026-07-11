from app.domain.compliance.entities import ComplianceViolation


class ComplianceViolationError(RuntimeError):
    """Raised when the Risk & Compliance Reviewer rejects a candidate output before persistence.

    Follows the `InsufficientEvidenceError` precedent exactly
    (`application/signals/insufficient_evidence_error.py`): a plain `RuntimeError` subclass
    carrying enough structured detail (`source`, `violations`) for a router to turn it into a
    422, raised right before the repository `.create(...)` call. Issue #9 is explicit that
    non-compliant output must be rejected or flagged, never silently persisted — this is the
    "reject" half of that contract; there is no auto-retry loop.
    """

    def __init__(self, source: str, violations: list[ComplianceViolation]) -> None:
        detail = "; ".join(f"{violation.rule}: {violation.detail}" for violation in violations)
        super().__init__(f"Compliance check failed for {source}: {detail}")
        self.source = source
        self.violations = violations
