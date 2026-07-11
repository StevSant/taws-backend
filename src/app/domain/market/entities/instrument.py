from dataclasses import dataclass

from app.domain.market.entities.asset_class import AssetClass


@dataclass(frozen=True, slots=True)
class Instrument:
    """A single tradable/trackable instrument in the curated universe."""

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
