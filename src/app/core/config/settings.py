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

    # Dev-only email->role fallback matching the frontend demo accounts. Consulted ONLY
    # in a dev env (see `resolve_user_role` / `dev_fallback_allowed`); in production the
    # role comes solely from the verified JWT claims, never from the email.
    demo_email_role_map: dict[str, str] = {
        "analista@midas.demo": "analyst",
        "gestor@midas.demo": "portfolio",
        "compliance@midas.demo": "compliance",
    }

    # Locale used for LLM-generated content (signals/briefings/scenarios) when a caller
    # doesn't supply one — e.g. a scheduled job, a chat tool call, or a request that omits
    # the `locale` field. BCP-47-ish tag, e.g. "en", "es", "es-MX".
    default_locale: str = "en"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # --- OpenAI Realtime voice agent (ephemeral-session mint + server-side tool dispatch) ---
    # Master switch; when False the DI container binds no realtime session provider and the
    # `/chat/realtime/*` endpoints return 503 (same "unconfigured -> degrade" pattern as the
    # other gated integrations in `Container`).
    openai_realtime_enabled: bool = False
    # SEPARATE, billed Realtime API key. MAY be left unset to reuse `openai_api_key` (the DI
    # container falls back to it) — realtime audio bills differently, so keep the option to
    # scope/rotate it independently once cost tracking matters.
    openai_realtime_api_key: str | None = None
    openai_realtime_model: str = "gpt-realtime-2.1-mini"
    openai_realtime_voice: str = "alloy"
    # TTL (seconds) of a minted ephemeral client secret (`ek_*`) before it expires — the
    # short-lived token the browser holds; the real key never leaves the backend.
    openai_realtime_ttl_seconds: int = 600

    # --- Text-to-Speech (voice playback of assistant replies, behind the TTSProvider
    # port). Leaving TTS_API_KEY unset disables server-side TTS: chat still works,
    # POST /api/v1/chat/speak returns 503, and the frontend falls back to the browser's
    # built-in speech synthesis. Kept as its own key (not reusing OPENAI_API_KEY) so TTS
    # can be enabled/keyed/billed independently of the chat/embedding pipelines. ---
    tts_enabled: bool = False
    tts_provider: str = "openai"
    tts_api_key: str | None = None
    tts_model: str = "tts-1"
    tts_voice: str = "nova"
    tts_response_format: str = "mp3"
    # Max characters accepted per /speak request. Caps per-request TTS cost and stays
    # under OpenAI's ~4096-char synthesis limit. Tune down to tighten the cost blast radius.
    tts_max_input_chars: int = 4096

    # --- Speech-to-Text (dictate a chat message by voice, behind the STTProvider port).
    # The mirror image of TTS: an uploaded audio clip -> transcribed text. Leaving
    # STT_API_KEY unset disables server-side STT: chat still works, POST
    # /api/v1/chat/transcribe returns 503, and the frontend falls back to the browser's
    # built-in speech recognition. Kept as its own key (not reusing OPENAI_API_KEY) so
    # STT can be enabled/keyed/billed independently of the chat/embedding pipelines. ---
    stt_enabled: bool = False
    stt_provider: str = "openai"
    stt_api_key: str | None = None
    stt_model: str = "whisper-1"
    # Max audio bytes accepted per /transcribe request. 25 MiB matches Whisper's
    # per-file cap and caps per-request cost / DoS blast radius. Reject before hitting
    # the billed transcription API.
    stt_max_audio_bytes: int = 26214400

    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_jwt_secret: str | None = None
    # Retry-with-backoff applied around every Supabase*Repository client call (issue #7):
    # only transient network failures (DNS blips, dropped connections) are retried, never
    # application-level Postgrest errors. See `with_supabase_retry`.
    supabase_retry_max_attempts: int = 2
    supabase_retry_backoff_base_seconds: float = 0.2

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
    # Circuit breaker (issue #9): once a non-transient error (402 quota-exhausted/401
    # unauthorized, or 429 rate-limited) is seen, stop calling Marketaux for this many
    # minutes instead of retrying every poll. 402/401 (billing/config issues that won't
    # resolve themselves soon) use the longer cool-down; 429 (rate limiting) uses the
    # shorter one since it's likely to clear within the polling window.
    marketaux_cooldown_minutes: int = 20
    marketaux_rate_limit_cooldown_minutes: int = 5

    # --- NewsAPI.org (behind the NewsProvider port) ---
    newsapi_api_key: str | None = None
    newsapi_base_url: str = "https://newsapi.org/v2"
    # Query used when no instrument symbols are requested (general market news).
    newsapi_default_query: str = "stocks OR crypto OR markets"
    # Circuit breaker (mirrors Marketaux, issue #9): the free tier caps at 100 requests/day
    # and this adapter is hit on every `/api/v1/news` poll, so once the quota/rate limit is
    # reached every subsequent request re-hits an already-failing API. After a 401/426
    # (key/quota/plan issue that won't clear soon) stop calling NewsAPI for this many
    # minutes; a 429 (rate limit) uses the shorter cool-down below since it clears sooner.
    newsapi_cooldown_minutes: int = 20
    newsapi_rate_limit_cooldown_minutes: int = 5

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
    # Short-TTL in-process cache in front of get_price_series/get_last_price (issue #8) —
    # CoinGecko's free tier rate-limits (429) hard when the same handful of crypto
    # instruments are polled every ~60s; a cache this short still keeps prices fresh
    # enough for the product's polling cadence while cutting redundant calls.
    coingecko_cache_ttl_seconds: float = 60.0
    # Optional free "Demo" API key (https://www.coingecko.com/en/api/pricing -> Demo plan):
    # sent as the `x-cg-demo-api-key` header to lift the keyless public rate limits
    # (~30 calls/min, 10k/month). Leave empty to use the keyless public API.
    coingecko_api_key: str = ""
    # Circuit-breaker backoff: once a live CoinGecko call fails (e.g. 429), stop calling it
    # for this many seconds and serve fixtures instead, so one rate-limit doesn't turn into
    # a per-request storm (the in-process cache only ever stores successful responses).
    coingecko_cooldown_seconds: float = 300.0

    # --- FRED (macro: rates, CPI; behind the MacroDataProvider port) ---
    # Free key at https://fred.stlouisfed.org/docs/api/api_key.html. Leave empty to serve
    # fixture rates/CPI instead (see RoutingMacroDataProvider/FixtureMacroDataProvider).
    fred_api_key: str | None = None
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    fred_rates_series_id: str = "FEDFUNDS"
    fred_cpi_series_id: str = "CPIAUCSL"
    # Additional "Contexto de mercado" indicators (issue #58): daily FRED series so their
    # sparkline history is dense. Gold = London PM fixing (USD/oz), oil = WTI spot (USD/bbl),
    # 10Y = 10-Year Treasury constant-maturity yield (%).
    fred_gold_series_id: str = "GOLDPMGBD228NLBM"
    fred_oil_series_id: str = "DCOILWTICO"
    fred_treasury_10y_series_id: str = "DGS10"
    fred_timeout_seconds: float = 10.0
    # Default/max number of observations returned by GET /api/v1/macro/series/{indicator}.
    macro_series_default_days: int = 90
    macro_series_max_days: int = 365

    # --- VIX (volatility regime, MacroDataProvider port; via yfinance, no key needed) ---
    vix_symbol: str = "^VIX"
    vix_low_threshold: float = 15.0
    vix_elevated_threshold: float = 20.0
    vix_high_threshold: float = 30.0

    # --- Fixture macro fallback values (used when FRED_API_KEY is unset or a live call fails) ---
    fixture_macro_rate: float = 5.25
    fixture_macro_cpi: float = 3.2
    fixture_macro_vix: float = 18.5
    fixture_macro_gold: float = 2350.0
    fixture_macro_oil: float = 78.0
    fixture_macro_treasury_10y: float = 4.25

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

    # Bounded retry around the Analyst's structured-output classification call
    # (`GenerateSignal._classify_impact`) before it degrades to an honest "uncertain,
    # analysis unavailable" fallback (issue #55). Covers transient failures only (rate
    # limit / timeout / malformed or unparseable structured output); a permanently
    # unavailable provider (no API key -> `LLMProviderUnavailableError`) is not retried.
    # `max_attempts` counts retries AFTER the first try (so 2 => up to 3 total calls);
    # backoff is exponential (`base * 2**(attempt-1)`), mirroring `with_supabase_retry`.
    signal_classification_retry_max_attempts: int = 2
    signal_classification_retry_backoff_base_seconds: float = 0.5

    # --- Pending news pre-filter (issues #3 + #26): the gate `AnalyzePendingNews._prefilter`
    # applies before spending an LLM classification call. Assembled into a
    # `NewsPrefilterPolicy` by `Container.get_news_prefilter_policy()` — the single place
    # these are read, so the HTTP endpoint and the scheduled tick can't drift apart. ---
    # Floor (0-1) below which a pending news item is skipped (analysis_status -> skipped,
    # skip_reason -> gated_low_relevance) without an LLM call. NOTE: since #26 this gates the
    # COMBINED relevance+materiality score below, not symbol-relevance alone.
    news_relevance_skip_threshold: float = 0.35
    # How the two components of that combined score are weighted (normalized by their sum, so
    # only their ratio matters). Materiality is what lets a genuinely important article that
    # never spells out a watchlist ticker survive the gate.
    news_prefilter_relevance_weight: float = 0.6
    news_prefilter_materiality_weight: float = 0.4
    # Relevance credited when an article is linked to an instrument by company/fund NAME
    # rather than by its ticker ("Apple unveils…" -> AAPL). Weaker evidence than an explicit
    # ticker, hence < 1.0 — but these used to score 0.0 and be gated out wholesale, which is
    # what made essentially every item show as "Sin clasificar" (issue #68).
    news_relevance_name_match_score: float = 0.6

    # --- News materiality signal (issue #26): the cheap, non-LLM "is this important enough to
    # be worth a token?" half of the pre-filter. See `compute_news_materiality_score`. ---
    # Market-moving event terms; the share of these found in an item's title+summary is the
    # score's main component. Whole-word matched, case-insensitive; multi-word entries allowed.
    news_materiality_keywords: list[str] = [
        "acquisition",
        "bankruptcy",
        "central bank",
        "default",
        "downgrade",
        "earnings",
        "fed",
        "guidance",
        "inflation",
        "interest rate",
        "ipo",
        "lawsuit",
        "layoffs",
        "merger",
        "rate cut",
        "rate hike",
        "recession",
        "reform",
        "regulation",
        "sanctions",
        "selloff",
        "stimulus",
        "tariff",
        "upgrade",
    ]
    # Publishers whose choosing to cover an event is itself evidence that it matters. Matched
    # against `NewsItem.source` (the article's own outlet), case-insensitively.
    news_materiality_high_impact_sources: list[str] = [
        "Bloomberg",
        "CNBC",
        "Financial Times",
        "Reuters",
        "The Wall Street Journal",
        "Yahoo Finance",
    ]
    # Relative weights of the four materiality components (normalized by their sum, so zeroing
    # one out reweights the others rather than shrinking the score's range).
    news_materiality_keyword_weight: float = 0.5
    news_materiality_source_weight: float = 0.2
    news_materiality_sentiment_weight: float = 0.15
    news_materiality_recency_weight: float = 0.15
    # Recency decays by half every this many hours since publication.
    news_materiality_recency_half_life_hours: float = 24.0
    # Keyword hits at or above this count saturate the keyword component at 1.0, so a
    # keyword-stuffed headline can't outscore a genuinely material one.
    news_materiality_keyword_saturation_count: int = 3

    # --- Pending news analysis batch pipeline (issue #2: POST /api/v1/news/analyze-pending
    # and its scheduled tick) ---
    # Master switch for the SCHEDULED tick only. Turning it off stops the background analysis
    # job from being registered at all (so no LLM spend happens unattended); the on-demand
    # `POST /api/v1/news/analyze-pending` and the manual per-item `POST /news/{id}/analyze`
    # keep working either way.
    news_analysis_enabled: bool = True
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

    # --- Gemini (Event Intelligence / Sentinel analyzer) ---
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    # --- Scenario synthesis resilience (issue #64) ---
    # Bounded retry around the Synthesis step's structured-output call. A transient
    # structured-output failure is retried up to this many attempts before the pipeline
    # surfaces an honest "analysis unavailable" error state, instead of degrading to a
    # zero-confidence pseudo-result with internal fallback markers.
    scenario_synthesis_max_attempts: int = 2

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
