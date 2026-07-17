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

    # Locale used for LLM-generated content (chat/signals/briefings/scenarios) when neither
    # the request nor the authenticated user's `preferred_locale` supplies one — e.g. a
    # scheduled job, an anonymous visitor, or a request that omits the `locale` field.
    # BCP-47-ish tag, e.g. "en", "es", "es-MX". `es` matches the frontend's default locale
    # (`core/i18n/translation-service.ts`); the two sides must agree (issue #67).
    default_locale: str = "es"

    openai_api_key: str | None = None
    # --- Tiered LLM models (issue #28) ---
    # Fast/default tier: routing, titling, tone scoring, scenario intake, news localization —
    # structured, low-reasoning calls where a cheap model is already correct.
    openai_model: str = "gpt-4o-mini"
    # Reasoning tier: impact signals, pending-news batch analysis, scenario synthesis, causal
    # chains, macro interpretation, watchlist briefings, and the 6 chat specialists. Left unset
    # ON PURPOSE: `reasoning_model` below falls back to `openai_model`, so behavior is identical
    # to today until an operator actually configures a stronger model. Never read this field
    # directly — read `reasoning_model`.
    openai_model_reasoning: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    # --- Agent-graph chat model tuning (latency/cost quick wins). Applied by
    # `infrastructure/llm/chat_model_factory.build_chat_model` to every ChatOpenAI it builds
    # (router + specialists); the no-API-key fallback model ignores them. ---
    # Per-request timeout (seconds) before a hung OpenAI call is abandoned, so one stalled
    # request can't pin a chat turn open indefinitely.
    openai_request_timeout_seconds: float = 60.0
    # Automatic retries ChatOpenAI performs on a transient/5xx/timeout failure before giving up.
    openai_max_retries: int = 2
    # Cap on tokens generated per chat-model completion — bounds the worst-case latency and cost
    # of a single reply. Passed to ChatOpenAI(max_tokens=...); a long multi-specialist answer that
    # exceeds it is silently truncated at finish_reason="length" (no error), so keep headroom.
    chat_max_output_tokens: int = 4096
    # Temperature for the ROUTER's structured route classification only (specialists keep the
    # model default). 0.0 makes the 1-of-6 route pick as deterministic as the provider allows.
    router_temperature: float = 0.0
    # How many trailing messages of the thread the router classifies. The router only needs the
    # latest turn to pick a route; 4 messages (~ the last 2 exchanges) is enough for a follow-up
    # like "and Tesla?" to inherit context without re-reading the whole accumulated history.
    router_history_max_messages: int = 4
    # Bounds the history splat sent to the specialist/contributor/synthesizer calls; 12 ~= the
    # last 6 exchanges. Trims only what is SENT to the model on long threads (the checkpointed
    # state is untouched), so per-call prompt growth stays bounded. The router has its own,
    # tighter `router_history_max_messages` above — classification needs less context than a reply.
    chat_history_max_messages: int = 12
    # Total attempts the post-stream background persistence of a chat turn makes before the
    # turn is dropped with a WARNING. The write is fire-and-forget (the client already has the
    # reply), so a failure never reaches the user — but an unpersisted turn leaves a "ghost"
    # conversation the frontend can never rehydrate. 3 spaced attempts outlive the brief
    # unavailability window an App Runner deploy opens. 1 = the historical no-retry behavior.
    chat_persist_retry_max_attempts: int = 3
    # Base seconds between those attempts (linear backoff: attempt * base).
    chat_persist_retry_backoff_seconds: float = 2.0

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
    # Tool-selection mode for the Realtime voice session. "required" forces a tool call on EVERY
    # turn, which drove a filler-preamble / self-response loop (the model narrating "let me
    # check…" just to satisfy the forced call); "auto" lets it answer directly and only call a
    # tool when one is actually needed. The frontend already overrides this to "auto" — this
    # stops the backend shipping the loop-prone default.
    openai_realtime_tool_choice: str = "auto"
    # Sampling temperature for the Realtime voice session. Lower than the text-chat models to
    # keep spoken replies focused and cut the rambling the loop amplified. NOTE: only the WS
    # `session.update` transport applies this — the GA `client_secrets.create` mint has no
    # temperature field (see `openai_realtime_session_provider.py`).
    openai_realtime_temperature: float = 0.6
    # server_vad turn-detection tuning for the Realtime session (both transports), replacing the
    # bare `{"type": "server_vad"}` default. `threshold` is the 0-1 VAD activation level;
    # `silence_ms` is how long a pause ends the user's turn; `create_response` auto-generates a
    # reply at end-of-turn; `interrupt_response` lets the user barge in over the model. Tuned to
    # make end-of-turn detection deterministic and stop the agent talking over itself.
    openai_realtime_vad_threshold: float = 0.5
    openai_realtime_vad_silence_ms: int = 500
    openai_realtime_vad_create_response: bool = True
    openai_realtime_vad_interrupt_response: bool = True

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

    # --- `GET /api/v1/news` read path (taws#71) ---
    # Serve the feed from the persisted `news_items` store (`ListRecentNews`) instead of
    # re-aggregating the upstream providers synchronously on the request path, which on a
    # cold cache overshot the radar client's request timeout and killed the whole page.
    # Kill switch: set False to restore the old always-blocking `IngestNews` behavior.
    news_db_first_enabled: bool = True
    # Persisted items a window must yield before it is served straight from the store.
    # Below this the store counts as cold and the request falls back to a blocking upstream
    # fetch, so the very first caller for a window/symbol still gets news. 1 = only fall
    # back when the store returns nothing at all.
    news_db_first_min_items: int = 1
    # Cadence (seconds) of the post-response upstream refresh that keeps `news_items` warm
    # (`NewsFeedRefresher`), per (symbol, asset_class, since_hours). The radar polls the
    # feed on an interval from every open browser; this is what stops those polls from
    # stampeding the upstream providers.
    news_refresh_min_interval_seconds: float = 120.0
    # Items requested from the upstream providers per background refresh run.
    news_refresh_limit: int = 50

    # --- CoinGecko (crypto prices, behind the MarketDataProvider port); no key required ---
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    # Short-TTL in-process cache in front of get_price_series/get_last_price (issue #8) —
    # CoinGecko's free tier rate-limits (429) hard when the same handful of crypto
    # instruments are polled every ~60s; a cache this short still keeps prices fresh
    # enough for the product's polling cadence while cutting redundant calls.
    coingecko_cache_ttl_seconds: float = 60.0
    # Free "Demo" API key(s) (https://www.coingecko.com/en/api/pricing -> Demo plan), sent as
    # the `x-cg-demo-api-key` header to lift the keyless public rate limits (~30 calls/min,
    # 10k/month). Accepts a COMMA-SEPARATED LIST for failover: `CG-aaa,CG-bbb`. Read through
    # the `coingecko_api_keys` property, never directly. Empty -> the keyless public API.
    #
    # The quota is metered per key, and CoinGecko issues one Demo key per account, so a second
    # key means a second account. All three CoinGecko adapters (prices, metadata, search) spend
    # from the same key, so a single key's ~30 calls/min is easy to exhaust from one dashboard.
    coingecko_api_key: str = ""
    # How long a key that got 429'd is benched before the ring tries it again. The Demo limit is
    # PER MINUTE, so ~60s is exactly how long a throttled key needs to recover — benching it for
    # the full `coingecko_cooldown_seconds` below would waste 4 minutes of good quota.
    coingecko_key_cooldown_seconds: float = 60.0
    # Circuit-breaker backoff: once CoinGecko itself is DOWN (5xx / unreachable), stop calling it
    # for this many seconds, so one outage doesn't turn into a per-request storm (the in-process
    # cache only ever stores successful responses). While backing off, crypto prices are reported
    # as unavailable — never faked.
    #
    # Rate limits (429) do NOT arm this breaker: they are handled per-key by `CoinGeckoKeyRing`
    # (bench the throttled key, retry the same request on the next one). Arming a provider-wide
    # 5-minute breaker on a 429 is what used to blank out EVERY crypto instrument the moment one
    # key ran out of quota.
    coingecko_cooldown_seconds: float = 300.0
    # Longest history CoinGecko's public/Demo tiers will serve: requests beyond this fail with
    # `error_code: 10012` ("request exceeds the allowed time range"). Requests are clamped to
    # it rather than sent and failed — the `max` chart timeframe asks for 1825 days, and that
    # 400 used to trip the circuit breaker and poison EVERY crypto price for the whole cooldown
    # window with fixture data. Raise this if you move to a paid plan with deeper history.
    coingecko_max_history_days: int = 365

    # --- yfinance (stocks/FX/commodities/credit ETFs, behind the MarketDataProvider port);
    # no key required ---
    # Short-TTL in-process cache in front of get_price_series/get_last_price (mirrors the
    # CoinGecko cache above): the radar polls the same handful of instruments from every open
    # browser every ~60s, and each read was a live Yahoo round-trip. Keyed by (ticker, days) for
    # series and by ticker for last price; only non-empty results are cached, so a transient
    # blank never pins an instrument as unavailable for the whole window. A little longer than
    # the CoinGecko default since equities/FX quotes move less second-to-second than crypto.
    yfinance_cache_ttl_seconds: float = 120.0

    # --- FRED (macro: rates, CPI; behind the MacroDataProvider port) ---
    # Free key at https://fred.stlouisfed.org/docs/api/api_key.html. REQUIRED for rates/CPI:
    # with no key those lookups raise `MacroDataUnavailableError` and the macro specialist
    # says so. They used to fall back to hardcoded fixture values, which is how a misconfigured
    # deployment could keep answering with confident invented rates and CPI prints forever.
    fred_api_key: str | None = None
    fred_base_url: str = "https://api.stlouisfed.org/fred"
    fred_rates_series_id: str = "FEDFUNDS"
    fred_cpi_series_id: str = "CPIAUCSL"
    # Additional "Contexto de mercado" indicators (issue #58): daily FRED series so their
    # sparkline history is dense. Oil = WTI spot (USD/bbl), 10Y = 10-Year Treasury
    # constant-maturity yield (%).
    fred_oil_series_id: str = "DCOILWTICO"
    fred_treasury_10y_series_id: str = "DGS10"
    # DEPRECATED — no longer used. FRED's free daily gold fixing (`GOLDPMGBD228NLBM`, the LBMA
    # London PM fixing) was discontinued, so gold now comes from yfinance `GC=F` (see
    # `yfinance_gold_symbol` below and `infrastructure/macro/yfinance_gold_series_source.py`).
    # Kept only so an existing `FRED_GOLD_SERIES_ID` in a deployed `.env` doesn't error on load.
    fred_gold_series_id: str = "GOLDPMGBD228NLBM"
    fred_timeout_seconds: float = 10.0
    # Short-TTL in-process cache in front of get_rates/get_cpi/get_volatility_regime (mirrors
    # the CoinGecko cache): these macro series move slowly (rates/CPI monthly, VIX daily) but
    # every macro-aware pipeline re-reads them per request. Longer default than the price caches
    # since the underlying data barely changes within half an hour; only successful reads are
    # cached, so a transient FRED/Yahoo failure still surfaces as MacroDataUnavailableError.
    fred_cache_ttl_seconds: float = 1800.0
    # Default/max number of observations returned by GET /api/v1/macro/series/{indicator}.
    macro_series_default_days: int = 90
    macro_series_max_days: int = 365

    # --- Gold "Contexto de mercado" series (MacroDataProvider port; via yfinance, no key
    # needed) --- COMEX gold futures continuous front-month, replacing the discontinued FRED
    # gold fixing. Same yfinance mechanism the VIX regime uses.
    yfinance_gold_symbol: str = "GC=F"

    # --- VIX (volatility regime, MacroDataProvider port; via yfinance, no key needed) ---
    vix_symbol: str = "^VIX"
    vix_low_threshold: float = 15.0
    vix_elevated_threshold: float = 20.0
    vix_high_threshold: float = 30.0

    # NOTE: the `fixture_macro_*` fallbacks (rate 5.25, CPI 3.2, VIX 18.5, gold 2350, oil 78,
    # 10Y 4.25) and the `fixture_fear_greed_*` pair used to live here. They are gone on purpose.
    # Every one of those was a plausible-looking number — nobody double-takes at "CPI 3.2%" the
    # way they would at "BTC $333" — so when a live call failed they were served, believed, and
    # narrated to users as measured fact. Do not reintroduce defaults of this shape: a config
    # default for a *market observation* is a fabrication with a settings key.

    # --- alternative.me (Crypto Fear & Greed Index; behind the FearGreedProvider port);
    # no key required ---
    alternative_me_base_url: str = "https://api.alternative.me"
    alternative_me_timeout_seconds: float = 10.0
    # Short-TTL in-process cache in front of get_fear_greed_index (mirrors the CoinGecko cache):
    # the index only updates ~once a day, yet every sentiment read re-fetched it live. Longest
    # default of the three caches for that reason; only a successful read is cached, so an outage
    # still surfaces as FearGreedUnavailableError rather than a stale value.
    fear_greed_cache_ttl_seconds: float = 3600.0

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

    # --- Per-article news sentiment (`ScoreNewsSentiment`) ---
    # Fills `news_items.sentiment_score`, which had no producer other than Marketaux's own
    # pass-through — every other adapter left it NULL, so the UI showed almost the whole corpus
    # as "Sin clasificar". Distinct from the per-INSTRUMENT tone pipeline (`AnalyzeSentiment`,
    # `sentiment_readings` table), which answers a different question and writes a different
    # table. Master switch for the SCHEDULED tick only, same rationale as
    # `news_analysis_enabled`: it is the job that spends LLM tokens unattended.
    news_sentiment_enabled: bool = True
    # Cadence (minutes) of the scoring tick. Also the backfill's rate: the pass takes unscored
    # rows newest-first, so the NULL backlog drains at `batch_limit` per tick.
    news_sentiment_poll_interval_minutes: int = 10
    # Max articles pulled per tick. Bounds the unattended LLM spend, and — since the same pass
    # backfills the existing NULL rows — decides how fast that archive drains.
    news_sentiment_batch_limit: int = 60
    # Articles scored per LLM call. Headlines are short and independent, so batching them keeps
    # the backfill's cost proportional to the work rather than to the size of the archive. Too
    # large and the model starts dropping entries from its response; ~15 is a safe ceiling.
    news_sentiment_chunk_size: int = 15

    # --- News detail payload (issue #57: GET /api/v1/news/{id}, via `BuildNewsDetail`) ---
    # Caps how many of an article's `related_symbols` get a live price lookup, since each one
    # costs a `ComputeMarketStats` call (an upstream market-data fetch). An article tagged with
    # 30 tickers is a linker artifact, not 30 chips worth rendering.
    news_detail_max_affected_instruments: int = 8
    # How many related articles the detail page's "related news" list carries. Paginated client
    # side, so this is the whole list, not a page.
    news_detail_related_limit: int = 12
    # Lookback for the affected-instrument chips' % change. Matches `ComputeMarketStats`'s own
    # default window, so a chip and the asset page it links to never disagree on the number.
    news_detail_price_window_days: int = 30

    # --- News browse page (issue #70: GET /api/v1/news/browse, the DB-backed archive with
    # numbered pagination — distinct from the live provider-fed GET /api/v1/news) ---
    # Page size used when the caller doesn't pass one, and the ceiling it's clamped to, so a
    # crafted `page_size` can't ask the store for an unbounded page.
    news_browse_default_page_size: int = 20
    news_browse_max_page_size: int = 100
    # abs(sentiment_score) at or below which a news item counts as *neutral* in the browse
    # sentiment filter; above it, positive/negative. Deliberately mirrors the frontend's
    # `classifyNewsSentiment` threshold — if the two drift, a card badged "positivo" could
    # disappear from the "positive" filter.
    news_sentiment_neutral_threshold: float = 0.15

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
    # Real data-source vendor labels stamped into `ChartMeta.source` (never the old generic
    # "market data"): crypto is priced by CoinGecko, every other asset class by Yahoo Finance
    # — the exact split `RoutingMarketDataProvider` routes on. Rendered as `Source: {…}`.
    market_source_crypto: str = "CoinGecko"
    market_source_equity: str = "Yahoo Finance"

    # --- Server-side chart image rendering (Telegram sendPhoto, behind ChartImageRenderer) ---
    # PNG canvas geometry for the matplotlib renderer. figsize(inches) = px / dpi.
    chart_image_width_px: int = 1000
    chart_image_height_px: int = 600
    chart_image_dpi: int = 100
    # On-brand dark/gold theme for the rendered PNGs. All colors come from here so the
    # matplotlib adapter hardcodes none of them.
    chart_image_background_color: str = "#0e1116"
    chart_image_text_color: str = "#e6e6e6"
    chart_image_grid_color: str = "#2a2f3a"
    chart_image_accent_color: str = "#d4af37"
    chart_image_up_color: str = "#16c784"
    chart_image_down_color: str = "#ea3943"

    # --- Track-5 seed data paths (packaged with the app) ---
    # These seed the instrument UNIVERSE and the scenario PRESETS — configuration, i.e. which
    # instruments exist and which scenarios are offered. There is deliberately no seed of
    # market *observations* (prices, news, macro prints): a canned observation is a claim about
    # the world that nobody measured. `news_fixture.json` lived here and is gone.
    universe_seed_path: Path = _MARKET_SEEDS_DIR / "universe.json"
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
    # How long the same instrument must stay quiet before its (unchanged) call may alert again.
    # The novelty guard is keyed on `(watchlist, symbol)` and always lets a CHANGED call through
    # immediately, so this only throttles an alert repeating the same direction. Without it, the
    # analysis-refresh job minting a fresh signal row every few minutes re-alerted the same
    # ticker on every scan and buried the user's chat with the bot.
    watchdog_alert_cooldown_minutes: int = 360
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
    gemini_model: str = "gemini-3.5-flash"

    # --- Sentinel automatic news alerts (poll news -> Gemini -> important? -> Telegram) ---
    # Master switch for the SCHEDULED scan. Off => nothing is broadcast automatically; the
    # manual paths (`POST /event-intelligence/demo`, `POST /telegram/send-test-news`) still
    # work. Like the other unattended-LLM jobs, this one spends Gemini tokens AND pushes
    # notifications to every linked user without anyone asking, so an operator must be able to
    # stop it without also losing the Watchdog's alerting.
    sentinel_alerts_enabled: bool = True
    # Minutes between scheduled Sentinel scans.
    sentinel_poll_interval_minutes: int = 15
    # How far back each scan looks for news. Should comfortably exceed the poll interval so a
    # brief outage doesn't silently skip a window; overlap is free, since already-analyzed
    # items are filtered by `ProcessedEventTracker` before any LLM call.
    sentinel_news_since_hours: int = 6
    # Articles pulled from the upstream providers per scan (before the already-seen filter).
    sentinel_news_fetch_limit: int = 30
    # Gemini's `importance` floor (0-1) an event must ALSO clear, on top of its own
    # `shouldNotify` boolean, before anyone is notified. Two gates on purpose: the boolean is
    # the model's judgment and can drift with a prompt or model change, and the blast radius
    # here is a push notification to every linked user.
    sentinel_importance_threshold: float = 0.7
    # High-importance floor (0-1) that ROUTES an already-important event to a market-wide
    # broadcast instead of watchlist-targeted delivery. An event that clears
    # `sentinel_importance_threshold` (the "notify at all" gate) but scores BELOW this floor is
    # sent only to users whose watchlist contains one of its affected assets; an event at or
    # above this floor is broadcast to every linked chat (a genuinely market-moving event is not
    # about one person's watchlist). Must be >= `sentinel_importance_threshold`.
    sentinel_broadcast_importance_threshold: float = 0.90
    # Hard cap on alerts sent per scan, applied AFTER sorting by importance. A chaotic morning
    # can produce a dozen "important" headlines at once; without this the first genuinely busy
    # day carpet-bombs everyone's phone and the bot gets muted. Anything dropped is logged.
    sentinel_max_alerts_per_run: int = 3
    # Max concurrent Gemini analysis calls inside one scan.
    sentinel_max_concurrency: int = 3
    # --- Sentinel relevance pre-gate (cheap, no-AI filter applied BEFORE any Gemini `analyze`
    # call, so tokens are only spent on articles that plausibly matter) ---
    # Track 2 (macro): market-moving keywords. A fetched, non-duplicate article is dropped before
    # analysis unless its raw title+description hits one of these OR a watchlisted symbol/company
    # name (track 1, drawn from the union of ALL users' watchlists). Whole-word/phrase matched,
    # case-insensitive; multi-word entries ("Federal Reserve") match as phrases. An empty list
    # disables the macro track — the watchlist track still runs.
    sentinel_macro_keywords: list[str] = [
        "Federal Reserve",
        "Fed",
        "interest rate",
        "rate cut",
        "rate hike",
        "inflation",
        "CPI",
        "PCE",
        "recession",
        "GDP",
        "unemployment",
        "jobs report",
        "OPEC",
        "crude oil",
        "Treasury",
        "bond yields",
        "tariff",
    ]
    # Shortest tracked-symbol length matched as a BARE ticker in the pre-gate. A 1-2 char ticker
    # ("A" = Agilent, "IT" = Gartner) collides with ordinary words even under whole-word matching
    # (the word-boundary anchor still fires on the article word "a"), so tickers shorter than this
    # are matched only via their canonical company name, never as a bare symbol. Names are always
    # matched regardless of the symbol's own length, so recall for short-ticker companies is kept.
    sentinel_min_symbol_match_length: int = 3

    # --- Scenario synthesis resilience (issue #64) ---
    # Bounded retry around the Synthesis step's structured-output call. A transient
    # structured-output failure is retried up to this many attempts before the pipeline
    # surfaces an honest "analysis unavailable" error state, instead of degrading to a
    # zero-confidence pseudo-result with internal fallback markers.
    scenario_synthesis_max_attempts: int = 2
    # Six specialist calls fan out in one panel; keep provider pressure bounded while
    # retaining true parallel execution. Each failure is isolated and recorded.
    scenario_agent_panel_max_concurrency: int = 6
    scenario_agent_panel_max_attempts: int = 2

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

    # --- Shared asset-analysis caching (issue #29) — see
    # `docs/specs/2026-07-12-shared-asset-analysis-caching-design.md`. Analysis is shared, not
    # per-user, so one LLM run per (instrument, locale) per TTL window is enough; these back the
    # `FreshnessPolicy` value object built by `Container.get_freshness_policy()`. ---
    # Freshness TTL per asset class: how long a persisted analysis counts as still current
    # before a generate call is allowed to spend another LLM run. Crypto moves fastest,
    # equities slowest; `default` covers the asset classes without a dedicated bucket
    # (credit, commodity) and any analysis with no instrument (preset scenarios).
    analysis_ttl_crypto_minutes: int = 15
    analysis_ttl_equity_minutes: int = 360
    analysis_ttl_fx_minutes: int = 60
    analysis_ttl_default_minutes: int = 180
    # Rows kept per `(instrument_symbol, locale)` after each write — a short audit trail that
    # stops `signals`/`scenarios`/`sentiment_readings` growing without bound. Older rows are
    # pruned; `historical_analogs` is a separately-indexed copy, so pruning sources is safe.
    analysis_retention_keep: int = 5
    # Master switch for the SCHEDULED refresh tick only (same rationale as
    # `news_analysis_enabled`): it is the job that spends LLM tokens unattended. Turning it off
    # leaves `POST /api/v1/analysis/refresh` and the on-demand generate endpoints working.
    analysis_refresh_enabled: bool = True
    # Cadence (minutes) of the background `RefreshTrackedAnalysis` tick that keeps every
    # watchlisted instrument's analysis warm, so user reads never pay for an inline LLM run.
    # One tick; the TTLs above decide staleness.
    analysis_refresh_poll_interval_minutes: int = 5
    # Locales the background job keeps warm. Analysis content is localized and `locale` is part
    # of the cache key, so a symbol is refreshed once per locale in this set.
    analysis_refresh_locales: list[str] = ["en", "es"]
    # Bounds concurrent generations inside one refresh tick, so a large watchlist union can't
    # fire unbounded concurrent LLM requests (same guard as `news_analysis_max_concurrency`).
    analysis_refresh_concurrency: int = 4
    # Whether the refresh tick also covers the WHOLE curated instrument universe, not just the
    # instruments somebody happens to have watchlisted. Off, the markets explorer is a
    # graveyard: it lists every instrument but only ever shows a signal for the watchlisted
    # few, so most rows render "Sin señal" forever no matter how much news breaks. The tick is
    # freshness-gated (`analysis_ttl_*`), so widening the scope costs a handful of indexed
    # SELECTs per already-fresh symbol, not an LLM run.
    analysis_refresh_cover_universe: bool = True
    # Hard ceiling on symbols refreshed per tick, so growing the universe can't silently grow
    # the unattended LLM bill. Watchlisted instruments are always taken FIRST, so raising the
    # universe's size can never starve an instrument a user actually pinned.
    analysis_refresh_max_symbols: int = 40

    @property
    def reasoning_model(self) -> str:
        """The model used by the reasoning-tier call sites (issue #28).

        Falls back to `openai_model` when `OPENAI_MODEL_REASONING` is unset, so the tiering
        is a no-op until a stronger model is actually configured. This property is the ONLY
        place that fallback lives — no call site reads `openai_model_reasoning` directly.
        """
        return self.openai_model_reasoning or self.openai_model

    @property
    def coingecko_api_keys(self) -> list[str]:
        """The CoinGecko Demo keys, in failover order (primary first). Empty -> keyless.

        `COINGECKO_API_KEY` holds either one key or a comma-separated list, and this property
        is the ONLY place that is parsed — no call site reads `coingecko_api_key` directly.
        Overloading the existing var (rather than adding a second one) keeps a single key with
        no comma behaving exactly as before, and means adding a fallback key in production is a
        secret-VALUE change, with no Terraform/App Runner env plumbing to touch. A comma is not
        a legal character in a CoinGecko key (`CG-` + alphanumeric), so the split is unambiguous.
        """
        return [key.strip() for key in self.coingecko_api_key.split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()
