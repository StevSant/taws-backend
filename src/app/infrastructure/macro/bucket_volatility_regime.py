from app.domain.market.entities import VolatilityLevel


def bucket_volatility_regime(
    vix_level: float, low_threshold: float, elevated_threshold: float, high_threshold: float
) -> VolatilityLevel:
    """Bucket a raw VIX level into a `VolatilityLevel`, using configured thresholds.

    Shared by `FredMacroDataProvider` (live VIX) and `FixtureMacroDataProvider` (fixture VIX) so
    the bucketing rule never drifts between the two. Thresholds come from `Settings` (see
    `Settings.vix_low_threshold` / `vix_elevated_threshold` / `vix_high_threshold`), never
    hardcoded here.
    """
    if vix_level < low_threshold:
        return VolatilityLevel.LOW
    if vix_level < elevated_threshold:
        return VolatilityLevel.NORMAL
    if vix_level < high_threshold:
        return VolatilityLevel.ELEVATED
    return VolatilityLevel.HIGH
