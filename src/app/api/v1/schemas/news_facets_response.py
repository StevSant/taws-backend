from pydantic import BaseModel, ConfigDict


class NewsFacetsResponse(BaseModel):
    """Distinct filter values for the news browse page's source / provider dropdowns."""

    model_config = ConfigDict(from_attributes=True)

    sources: list[str]
    providers: list[str]
