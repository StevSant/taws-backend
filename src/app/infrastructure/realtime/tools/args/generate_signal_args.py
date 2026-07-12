from pydantic import BaseModel, Field


class GenerateSignalArgs(BaseModel):
    """Validated arguments for the `generate_signal` realtime tool.

    `symbol` is required; `locale` is optional (BCP-47-ish) and defaults to the app's
    configured locale when omitted. Extra fields are rejected.
    """

    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=32)
    locale: str | None = Field(default=None, max_length=16)
