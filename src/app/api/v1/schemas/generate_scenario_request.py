from pydantic import BaseModel, Field, model_validator


class GenerateScenarioRequest(BaseModel):
    """Request payload for `POST /api/v1/scenarios/generate` — either a curated preset id
    or free-form text, never both left unset.

    `preset_id` takes precedence if a caller somehow sends both (see
    `NormalizeScenarioIntake.execute`); this validator only rejects the "neither given"
    case, which `use_cases.NormalizeScenarioIntake` would otherwise reject deeper in the
    pipeline via `InvalidScenarioIntakeError` — validating here surfaces a clean `422`
    at the API boundary instead.
    """

    preset_id: str | None = Field(default=None, min_length=1, max_length=100)
    free_text: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _require_preset_or_free_text(self) -> "GenerateScenarioRequest":
        if not self.preset_id and not self.free_text:
            raise ValueError("Either preset_id or free_text must be provided.")
        return self
