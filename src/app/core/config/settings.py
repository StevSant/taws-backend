from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Packaged seeds dir, computed relative to this module (not CWD) so seed paths
# resolve correctly regardless of where the process is launched from.
_MARKET_SEEDS_DIR = Path(__file__).resolve().parent.parent.parent / "infrastructure" / "seeds"


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / `.env`.

    No value here is hardcoded elsewhere in the codebase — every URL, key, model name,
    or threshold that the app needs must be added as a field on this class.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: list[str] = ["http://localhost:4200"]

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_jwt_secret: str | None = None

    database_url: str | None = None

    # Marketaux news API (entity linkage + sentiment enrichment). Without a key the
    # adapter returns no items, letting other news sources / fixtures carry the load.
    marketaux_api_key: str | None = None
    marketaux_base_url: str = "https://api.marketaux.com/v1"
    marketaux_languages: str = "en"
    marketaux_timeout_seconds: float = 10.0
    # Free plan returns max 3 articles per request and 100 requests/day; keep the
    # per-fetch pagination small so scheduled polls stay within quota.
    marketaux_max_pages: int = 3

    # --- NewsAPI.org (behind the NewsProvider port) ---
    newsapi_api_key: str | None = None
    newsapi_base_url: str = "https://newsapi.org/v2"
    # Query used when no instrument symbols are requested (general market news).
    newsapi_default_query: str = "stocks OR crypto OR markets"

    # --- Finnhub (company-news, behind the NewsProvider port) ---
    finnhub_api_key: str | None = None
    finnhub_base_url: str = "https://finnhub.io/api/v1"

    # --- RSS feeds (behind the NewsProvider port); no key required ---
    rss_feed_urls: list[str] = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://finance.yahoo.com/news/rssindex",
    ]

    # --- CoinGecko (crypto prices, behind the MarketDataProvider port); no key required ---
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"

    # --- Track-5 seed data paths (packaged with the app; override for custom fixtures) ---
    universe_seed_path: Path = _MARKET_SEEDS_DIR / "universe.json"
    news_fixture_seed_path: Path = _MARKET_SEEDS_DIR / "news_fixture.json"
    preset_scenarios_seed_path: Path = _MARKET_SEEDS_DIR / "preset_scenarios.json"

    # Upstash Redis URL. Leave unset to use the in-memory checkpointer fallback.
    redis_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
