from pydantic import BaseModel, Field


class ListSignalsArgs(BaseModel):
    """Validated arguments for the `list_signals` realtime tool.

    `symbol` is required — signals are always listed for one instrument. Extra fields
    are rejected.
    """

    model_config = {"extra": "forbid"}

    symbol: str = Field(min_length=1, max_length=32)
