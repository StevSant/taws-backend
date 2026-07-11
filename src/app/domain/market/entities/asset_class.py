from enum import StrEnum


class AssetClass(StrEnum):
    """Broad category an `Instrument` belongs to."""

    STOCK = "stock"
    CRYPTO = "crypto"
    CREDIT = "credit"
    COMMODITY = "commodity"
    FOREX = "forex"
