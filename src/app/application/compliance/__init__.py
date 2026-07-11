"""Compliance application layer: the Risk & Compliance Reviewer (agent fleet #6, T1).

A review pass, not a chat specialist — never routed through `SupervisorRoute` or the chat
graph. `ReviewCompliance` (`application/compliance/use_cases/review_compliance.py`) is a
plain, dependency-free use case called synchronously by `GenerateSignal` and
`GenerateBriefing` as the final gate before persistence, and is reusable as-is by the future
Scenario Simulation graph's step 6 "Compliance" node (issue #12, not yet built — see
`review_compliance.py`'s docstring for the integration note left for that author).
"""

from app.application.compliance.compliance_violation_error import ComplianceViolationError

__all__ = ["ComplianceViolationError"]
