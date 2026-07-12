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

    # Locale used for LLM-generated content (signals/briefings/scenarios) when a caller
    # doesn't supply one — e.g. a scheduled job, a chat tool call, or a request that omits
    # the `locale` field. BCP-47-ish tag, e.g. "en", "es", "es-MX".
    default_locale: str = "en"

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
    # `feedparser.parse` has no timeout of its own; bounds each feed fetch/parse so one
    # stalled feed can't hang the whole `fetch_news` call (see `RssNewsProvider`).
    rss_feed_timeout_seconds: float = 3.0

    # Caps each live news adapter call and the overall fan-out budget before the
    # fixture fallback kicks in (see `AggregatingNewsProvider`).
    news_provider_timeout_seconds: float = 2.5
    news_live_fetch_budget_seconds: float = 3.5

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

    # --- alternative.me (Crypto Fear & Greed Index; behind the FearGreedProvider port);
    # no key required ---
    alternative_me_base_url: str = "https://api.alternative.me"
    alternative_me_timeout_seconds: float = 10.0

    # --- Fixture Fear & Greed fallback values (used when alternative.me is unreachable or
    # returns an unparseable payload) ---
    fixture_fear_greed_value: int = 50
    fixture_fear_greed_classification: str = "Neutral"

    # --- Sentiment Analyst tone bucketing thresholds (tone_score -> SentimentLabel);
    # tone_score >= bullish -> bullish, tone_score <= bearish -> bearish, else neutral ---
    sentiment_bullish_threshold: float = 0.15
    sentiment_bearish_threshold: float = -0.15

    # --- SEC EDGAR "latest filings" feed (behind the NewsProvider port); no key required.
    # SEC requires a descriptive User-Agent identifying the requester on every request
    # (https://www.sec.gov/os/webmaster-faq#developers) — set SEC_EDGAR_USER_AGENT to a
    # real app/company name + contact email before deploying publicly. ---
    sec_edgar_enabled: bool = True
    sec_edgar_user_agent: str = "TAWS Hackathon research@taws.dev"
    sec_edgar_feed_urls: list[str] = [
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company="
        "&dateb=&owner=include&count=100&output=atom"
    ]
    # Same rationale as `rss_feed_timeout_seconds` (see `SecEdgarNewsProvider`).
    sec_edgar_feed_timeout_seconds: float = 3.0

    # --- Fundamentals / earnings calendar (behind the FundamentalsProvider port); yfinance,
    # no key required ---
    # "Upcoming earnings risk" is flagged when the next earnings date falls within this many
    # days of now — a simple derived tag, not a risk model.
    upcoming_earnings_risk_window_days: int = 7

    # --- Analyst signal generation (HU1 acceptance criterion: "≥2 news sources with
    # source + date attached to each signal"); see `GenerateSignal` in
    # `application/signals/use_cases/generate_signal.py` ---
    min_distinct_news_sources: int = 2

    # --- Pending news pre-filter (issue #3): cheap-relevance floor (see
    # `compute_news_relevance_score`) below which a pending news item is skipped
    # (analysis_status -> skipped) without an LLM call. ---
    news_relevance_skip_threshold: float = 0.35

    # --- Pending news analysis batch pipeline (issue #2: POST /api/v1/news/analyze-pending
    # and its scheduled tick) ---
    # Bounds concurrent `GenerateSignal` calls fanned out by `AnalyzePendingNews`, so a
    # large pending backlog can't fire unbounded concurrent LLM requests.
    news_analysis_max_concurrency: int = 5
    # Max pending news items processed per `AnalyzePendingNews.execute()` run/tick.
    news_analysis_batch_limit: int = 200
    # Cadence (minutes) of the scheduled background tick that calls `AnalyzePendingNews`,
    # so newly-ingested news gets analyzed even while no user is on the page. Reuses the
    # same APScheduler infra as the Watchdog jobs (`infrastructure/scheduling`).
    news_analysis_poll_interval_minutes: int = 15

    # --- Historical analogs RAG (behind the VectorStore port, pgvector-backed) ---
    historical_analogs_top_k: int = 3

    # --- Chart visualizations (inline agent charts, behind the ChartConfig value object) ---
    # Master switch; when False the DI container binds no chart tools to any specialist.
    charts_enabled: bool = True
    # Default timeframe a chart tool uses when the LLM omits one.
    chart_default_timeframe: str = "1y"
    # Timeframe labels offered to the user (drives the frontend timeframe buttons — never
    # hardcode these client-side).
    chart_available_timeframes: list[str] = ["1m", "3m", "6m", "1y", "max"]
    # Timeframe label -> days of history to fetch. Keys must cover every available label.
    chart_timeframe_days: dict[str, int] = {
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "1y": 365,
        "max": 1825,
    }
    # Downsample cap: max points/bars shipped to the browser per series (perf guard).
    chart_max_points: int = 500

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

    # --- Scenario Monitors (arm a saved ScenarioResult as a Watchdog rule, issue #18) ---
    # How long an armed monitor stays active before auto-expiring with no match. Product
    # guidance: keep within a 7-30 day window; 14 days is the chosen middle default.
    scenario_monitor_ttl_days: int = 14
    # Absolute price-move % (over the window since arming) that counts as a match for each
    # `ScenarioSpec.magnitude` bucket — see `EvaluateScenarioMonitors`'s docstring for the
    # full matching-rule writeup and rationale for these specific numbers.
    scenario_monitor_price_move_threshold_low_pct: float = 2.0
    scenario_monitor_price_move_threshold_medium_pct: float = 5.0
    scenario_monitor_price_move_threshold_high_pct: float = 10.0
    # Cap on the "since arming" price-history window `EvaluateScenarioMonitors` requests
    # from `ComputeMarketStats`, so a monitor armed a long time ago doesn't trigger an
    # unbounded history fetch on every scan.
    scenario_monitor_price_window_max_days: int = 30


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
