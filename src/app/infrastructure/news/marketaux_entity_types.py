from app.domain.market.entities import AssetClass

# Marketaux `entity_types` filter values per domain asset class. CREDIT and
# COMMODITY have no Marketaux equivalent, so they are intentionally absent —
# the adapter simply skips the filter for them.
ASSET_CLASS_TO_ENTITY_TYPES: dict[AssetClass, str] = {
    AssetClass.STOCK: "equity,etf,index",
    AssetClass.CRYPTO: "cryptocurrency",
    AssetClass.FOREX: "currency",
}
