from enum import StrEnum


class ImpactMagnitude(StrEnum):
    """How large a `MacroAssetClassImpact`'s effect on an asset class is expected to be.

    Free-standing enum, own bounded context — not shared with `domain/scenario`'s
    `ScenarioMagnitude` (that enum describes how large a scenario's *triggering event*
    is; this one describes how large *one asset class's resulting impact* is), same
    "own bounded context" convention `ScenarioMagnitude`'s docstring documents for
    itself relative to `domain/market`'s `VolatilityLevel`.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
