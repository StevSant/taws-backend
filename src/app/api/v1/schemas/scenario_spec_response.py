from pydantic import BaseModel, ConfigDict

from app.domain.market.entities import AssetClass
from app.domain.scenario.entities import ScenarioHorizon, ScenarioMagnitude


class ScenarioSpecResponse(BaseModel):
    """Response payload for the normalized `ScenarioSpec` embedded in a `ScenarioResult`."""

    model_config = ConfigDict(from_attributes=True)

    entity: str
    event_type: str
    magnitude: ScenarioMagnitude
    horizon: ScenarioHorizon
    title: str
    description: str
    affected_symbols: list[str]
    affected_asset_classes: list[AssetClass]
    preset_id: str | None = None
