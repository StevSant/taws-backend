class ScenarioSynthesisUnavailableError(RuntimeError):
    """Raised when scenario synthesis genuinely cannot produce a real structured result.

    The Synthesis step calls `LLMProvider.complete_structured` behind a bounded retry
    (`Settings.scenario_synthesis_max_attempts`). When every attempt fails — no
    `OPENAI_API_KEY` configured, a transport/provider error, or a response that never
    validates against the schema — this is raised instead of fabricating a zero-confidence
    pseudo-result carrying internal fallback markers (issue #64). The scenarios router
    translates it into an honest, localized "analysis unavailable" error state for the UI,
    rather than presenting a fake result.
    """

    def __init__(self, scenario_title: str) -> None:
        super().__init__(f"Scenario synthesis unavailable for '{scenario_title}'.")
        self.scenario_title = scenario_title
