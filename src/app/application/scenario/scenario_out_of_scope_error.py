class ScenarioOutOfScopeError(ValueError):
    """Raised when Scenario Lab intake receives a description with no market, economic, or
    financial dimension — a personal, relationship, sports, or entertainment "what if" that
    the pipeline should refuse rather than dutifully analyzing as if it moved markets.

    The Intake step's structured extraction now returns an `is_market_relevant` flag; when
    it is false, `NormalizeScenarioIntake` raises this with the model-written, user-facing
    `rejection_reason` (in the user's locale). Distinct from `InvalidScenarioIntakeError`
    (which means "no input given at all"): this means "input given, but out of scope". Both
    the REST router and the chat tool translate it into a clean, honest refusal instead of a
    fabricated love-triangle scenario. Carries the reason as its message so callers can
    surface it verbatim (`422` detail / chat reply).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
