from dataclasses import dataclass, field

from app.domain.compliance.entities.compliance_violation import ComplianceViolation


@dataclass(frozen=True, slots=True)
class ComplianceCheckResult:
    """Outcome of one Risk & Compliance Reviewer pass over a candidate Analyst/Advisor/
    Scenario output (agent fleet #6, T1).

    `passed` is `True` if and only if `violations` is empty — callers gate on `passed`,
    not on the absence of an exception, since the review use case (`application/compliance/
    use_cases/review_compliance.py`) returns this result rather than raising; it's the
    caller's job (e.g. `GenerateSignal`, `GenerateBriefing`) to turn a failed result into a
    `ComplianceViolationError` right before persistence.
    """

    passed: bool
    violations: list[ComplianceViolation] = field(default_factory=list)
