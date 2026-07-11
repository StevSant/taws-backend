from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComplianceViolation:
    """One specific rule the Risk & Compliance Reviewer found broken in a candidate output.

    `rule` is a short, machine-stable identifier (e.g. `"disclaimer_missing"`,
    `"banned_phrase"`) for programmatic handling/logging; `detail` is the human-readable
    explanation surfaced through `ComplianceViolationError`
    (`application/compliance/compliance_violation_error.py`).
    """

    rule: str
    detail: str
