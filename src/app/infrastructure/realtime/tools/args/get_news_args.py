from pydantic import BaseModel, Field


class GetNewsArgs(BaseModel):
    """Validated arguments for the `get_news` realtime tool.

    `symbol` is optional (omit for general market news). `limit` bounds how many items
    come back so a tool call can't request an unbounded fetch. Extra fields rejected.
    """

    model_config = {"extra": "forbid"}

    symbol: str | None = Field(default=None, max_length=32)
    limit: int = Field(default=5, ge=1, le=25)
