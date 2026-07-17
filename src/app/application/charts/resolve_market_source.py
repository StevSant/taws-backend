from app.domain.market.entities import AssetClass


def resolve_market_source(asset_class: AssetClass, crypto_source: str, equity_source: str) -> str:
    """Map an instrument's asset class to the REAL vendor that priced it, for `meta.source`.

    Crypto is served by CoinGecko; every other asset class (equity, ETF, FX, commodity,
    credit) is served by yfinance/Yahoo Finance — the exact split
    `RoutingMarketDataProvider` routes on. Both vendor labels come from `Settings`
    (`market_source_crypto` / `market_source_equity`), never hardcoded here, so the price
    charts cite the actual data provider instead of the old generic ``"market data"``."""
    return crypto_source if asset_class == AssetClass.CRYPTO else equity_source
