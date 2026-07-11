class InvalidScenarioIntakeError(ValueError):
    """Raised when Scenario Lab intake is given neither a preset id nor free-form text.

    Defense in depth: `GenerateScenarioRequest` (the REST schema) already validates this
    at the API boundary, but `NormalizeScenarioIntake` is also called directly from the
    chat tool (`infrastructure/agents/tools/run_scenario_simulation_tool.py`), which has
    no schema-level validation in front of it — see that use case's docstring.
    """

    def __init__(self) -> None:
        super().__init__("Scenario intake requires either preset_id or free_text.")
