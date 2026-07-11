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

    # --- FRED (macro: rates, CPI; behind the MacroDataProvider port) ---
    # Free key at https://fred.stlouisfed.org/docs/api/api_key.html. Leave empty to serve
    # fixture rates/CPI instead (see RoutingMacroDataProvider/FixtureMacroDataProvider).
    fred_api_key: str | None = None
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    fred_rates_series_id: str = "FEDFUNDS"
    fred_cpi_series_id: str = "CPIAUCSL"
    fred_timeout_seconds: float = 10.0

    # --- VIX (volatility regime, MacroDataProvider port; via yfinance, no key needed) ---
    vix_symbol: str = "^VIX"
    vix_low_threshold: float = 15.0
    vix_elevated_threshold: float = 20.0
    vix_high_threshold: float = 30.0

    # --- Fixture macro fallback values (used when FRED_API_KEY is unset or a live call fails) ---
    fixture_macro_rate: float = 5.25
    fixture_macro_cpi: float = 3.2
    fixture_macro_vix: float = 18.5

    # --- Fundamentals / earnings calendar (behind the FundamentalsProvider port); yfinance,
    # no key required ---
    # "Upcoming earnings risk" is flagged when the next earnings date falls within this many
    # days of now — a simple derived tag, not a risk model.
    upcoming_earnings_risk_window_days: int = 7

    # --- Historical analogs RAG (behind the VectorStore port, pgvector-backed) ---
    historical_analogs_top_k: int = 3

    # --- Track-5 seed data paths (packaged with the app; override for custom fixtures) ---
    universe_seed_path: Path = _MARKET_SEEDS_DIR / "universe.json"
    news_fixture_seed_path: Path = _MARKET_SEEDS_DIR / "news_fixture.json"
    preset_scenarios_seed_path: Path = _MARKET_SEEDS_DIR / "preset_scenarios.json"

    # Upstash Redis URL. Leave unset to use the in-memory checkpointer fallback.
    redis_url: str | None = None

    # --- Watchdog / Notifier (scheduled watchlist monitoring + alerts, issue #10) ---
    # Base URL of the deployed frontend, used to compose an alert's link-back URL. Never
    # hardcode a frontend URL anywhere else in the codebase — read it from here.
    frontend_base_url: str = "http://localhost:4200"
    # Config-driven scan cadence; keep within the product's 5-15 minute polling window.
    watchdog_poll_interval_minutes: int = 10
    # Minimum Analyst-signal confidence for the Watchdog to consider a signal
    # notification-worthy (see `RunWatchdogScan._is_notification_worthy`).
    watchdog_min_confidence: float = 0.6
    # UTC hour/minute the daily scheduled briefing run fires (issue #10 acceptance
    # criterion 4) — regenerates an Advisor briefing for every active watchlist.
    watchdog_daily_briefing_hour_utc: int = 13
    watchdog_daily_briefing_minute_utc: int = 0

    # --- Telegram bot (per-user alert delivery, behind the NotificationChannel port,
    # issue #14) --- Leave TELEGRAM_BOT_TOKEN unset to keep the graceful-degradation
    # fallback to LoggingNotificationChannel (see Container.get_notification_channel).
    telegram_bot_token: str | None = None
    # Bot's @username (no leading @), used to build the `https://t.me/<username>?start=
    # <token>` deep link returned by `POST /api/v1/telegram/link-token`.
    telegram_bot_username: str | None = None
    # Public HTTPS URL Telegram POSTs updates to; registered via `setWebhook` on boot.
    telegram_webhook_url: str | None = None
    # Optional shared secret Telegram echoes back as `X-Telegram-Bot-Api-Secret-Token` on
    # every webhook POST; verified by `api/v1/routers/telegram.py`. Leave unset to skip
    # verification (fine for local/dev; set it for any public deployment).
    telegram_webhook_secret: str | None = None
    # TTL for a generated `/start <token>` linking token before it expires unused.
    telegram_link_token_ttl_minutes: int = 15


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
