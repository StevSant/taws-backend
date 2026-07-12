from pydantic import BaseModel, ConfigDict, Field


class NewsBlurbSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=4000)


class LocalizeNewsBlurbsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(default="es", min_length=2, max_length=16)
    items: list[NewsBlurbSourceRequest] = Field(default_factory=list, max_length=12)


class NewsBlurbResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    blurb: str


class LocalizeNewsBlurbsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NewsBlurbResponse]
