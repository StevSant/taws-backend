# CLAUDE.md — taws-backend

Guidance for future Claude Code sessions working in this repo. Keep it practical; this
is a hackathon skeleton, not a framework.

## Architecture: hexagonal / clean architecture

Dependencies point **inward only**:

```
api → application → domain ← infrastructure
```

- `domain/` is PURE. No `fastapi`, `openai`, `redis`, `langgraph`, or any other vendor
  import may appear here — ever. It defines **entities** (plain dataclasses/pydantic
  models) and **ports** (`abc.ABC` + `@abstractmethod`).
- `application/` holds use cases that orchestrate ports via constructor injection.
  They know nothing about which adapter is behind a port.
- `infrastructure/` holds adapters that implement domain ports against a real vendor
  (OpenAI, Supabase, Redis, pgvector, LangGraph).
- `api/` is the only layer allowed to import FastAPI. Routers depend on use cases and
  ports (injected via `api/v1/dependencies/`), never on infrastructure classes
  directly.

**Rule of thumb:** if you're tempted to `import openai` (or fastapi, redis, langgraph)
inside `domain/` or `application/`, stop — that logic belongs in `infrastructure/` or
`api/` instead.

## Conventions (strict, don't deviate)

- **One class/function per file (SRP).** Never group multiple classes in one file — this
  applies everywhere, including entities and enums (e.g. `MessageRole` and `Message`
  are two separate files). Don't let files grow large with code that mixes
  responsibilities: each file has one focused purpose — if it's accumulating several
  definitions or concerns, split it.
- **Package re-exports.** Every `__init__.py` re-exports its package's public symbols
  with `__all__`, so consumers import from the package, not the file:
  ```python
  # Good
  from app.infrastructure.llm import OpenAIProvider
  # Bad — reaches into the implementation file
  from app.infrastructure.llm.openai_provider import OpenAIProvider
  ```
  **When you add a new file, update the parent `__init__.py` in the same change.**
- **No hardcoded values.** Every URL, key, model name, or threshold comes from
  `Settings` (`app/core/config/settings.py`), which reads from `.env` via
  pydantic-settings. If you catch yourself writing a literal API URL, model string, or
  timeout — stop, add a field to `Settings`, wire it through `.env` and `.env.example`.
- **No tests during the hackathon.** Accepted risk (see the architecture spec's
  decision ledger). If a bug needs a regression test mid-hackathon, add a minimal
  `pytest` test next to the code under test — don't build out a suite.

## How to add things

### Add a new LLM provider for plain (non-agent) completions

Used by anything calling the `LLMProvider` port directly (not via the agent graph) —
currently unwired to a router, kept as a swap-point building block.

1. Create `infrastructure/llm/<vendor>_provider.py` implementing `LLMProvider`
   (`complete()`, `stream()`). See `infrastructure/llm/anthropic_provider.py` for the
   stub shape.
2. Re-export it from `infrastructure/llm/__init__.py`.
3. In `core/di/container.py`, change `Container.get_llm_provider()` to return the new
   adapter (probably gated by a new `Settings` field, e.g. `llm_provider: str`).

Nothing in `application/` or `api/` needs to change — that's the point of the port.

### Swap the LLM provider used by agent graphs (LangGraph)

Agent graphs (`infrastructure/agents/supervisor_graph.py`) don't go through `LLMProvider` —
they run on a LangChain `BaseChatModel`, built by `infrastructure/llm/chat_model_factory.
build_chat_model(settings, model, *, temperature=None)`. **This factory function is the swap
point** for agent-side providers (OpenAI → Anthropic/Gemini/Ollama/...):

1. Change `build_chat_model` to return a different LangChain chat model (e.g.
   `ChatAnthropic(...)` from `langchain-anthropic`), gated by a `Settings` field if you
   need to pick at runtime. It currently hardcodes `ChatOpenAI` — the one remaining
   provider-level hardcode, by design.
2. Nothing in `supervisor_graph.py`, `langgraph_agent_runner.py`, or `api/` needs to change —
   all only depend on LangChain's `BaseChatModel` interface.
3. Without `settings.openai_api_key`, the factory returns a fallback model
   (`infrastructure/llm/fallback_chat_model.build_fallback_chat_model`, a
   `GenericFakeChatModel` from `langchain_core`) that streams a placeholder reply
   token-by-token instead of crashing — preserve that guard in any replacement factory.

### Add a new port + adapter (e.g. a new capability)

1. Define the abstract port in `domain/<feature>/ports/<name>.py` (`ABC` +
   `@abstractmethod`). Re-export from that package's `__init__.py`.
2. Implement one or more adapters in `infrastructure/<area>/<name>.py`. Re-export from
   that package's `__init__.py`.
3. Wire it into `core/di/container.py` with a `get_<name>()` accessor.
4. If a use case needs it, inject the port (not the adapter) into the use case's
   constructor.

### Add a new router

1. Create `api/v1/routers/<name>.py` with an `APIRouter`.
2. Re-export it (aliased, e.g. `router as <name>_router`) from
   `api/v1/routers/__init__.py`.
3. `include_router` it in `main.py`'s `create_app()`.
4. Add request/response schemas in `api/v1/schemas/` (one Pydantic model per file,
   re-exported).
5. Pull dependencies (current user, providers, repos) from `api/v1/dependencies/` —
   add a new `get_<thing>.py` there if needed, resolving via `core/di`.

### Add a new Supabase schema migration

Migrations are managed by [Alembic](https://alembic.sqlalchemy.org/) (`backend/alembic.ini`,
`script_location = migrations`) — see `migrations/README.md` for the full command
reference. **No SQLAlchemy ORM models / autogenerate**: the runtime data layer is
`supabase-py`, not SQLAlchemy, so every revision is hand-written raw SQL.

1. `uv run alembic revision -m "<short description>"` scaffolds an empty revision
   under `migrations/versions/`.
2. Write the schema change as raw SQL in `upgrade()` (via `op.execute(...)`), and its
   inverse in `downgrade()`. Follow the RLS pattern in `0001_watchlists_signals_briefings.py`
   — enable RLS and scope policies to `auth.uid()` on any new per-user table.
3. `uv run alembic upgrade head` applies it (needs `DATABASE_URL` in `.env` — the
   direct Postgres connection string from the Supabase project's *Database* settings).
4. Never add trading/execution columns (`buy`/`sell`/`order`/`quantity`/`price_target`)
   — this product's compliance stance is alert/task records only.

## Environment / settings rule

`Settings` in `core/config/settings.py` is the only place env vars are read. Every
field must exist in `.env.example` with a placeholder and a short comment. The durable
agent checkpointer is now Postgres, keyed off `DATABASE_URL` (the same direct connection
string the vector store and Alembic use). `REDIS_URL` is a LEGACY fallback and optional;
leave both unset locally and `Container.get_agent_memory()` uses `InMemoryCheckpointer`
automatically. `initialize_agent_memory()` (awaited in `main.py`'s lifespan) builds the
Postgres checkpointer and degrades to in-memory with a loud log — never a boot crash —
when `DATABASE_URL` is set but unreachable.

## uv commands

```bash
uv sync                 # install/update deps from pyproject.toml + uv.lock
uv add <package>         # add a runtime dependency
uv add --dev <package>   # add a dev-only dependency (linters, type checkers)
uv remove <package>      # remove a dependency
uv run <command>         # run anything inside the project's venv, e.g.:
uv run uvicorn app.main:app --reload
uv run ruff check .
uv run ruff format .
uv run pyright
```

Never use bare `pip`, `python -m`, or a bare `python` invocation — always `uv run`.

## Agent layer (LangGraph Supervisor) and streaming (SSE)

`POST /api/v1/chat/stream` is routed through the agent layer end to end:

```
chat.py router → StreamAndPersistReply → StreamReply use case → AgentRunner port
      → LangGraphAgentRunner adapter → compiled Supervisor graph
```

### The Supervisor graph

`infrastructure/agents/supervisor_graph.build_supervisor_graph(router_model, specialist_model,
scope_model, checkpointer, ...)` builds the default chat graph. A cheap **`supervisor`** router
node classifies each turn into **1–3 routes**, then:

- **1 route** → a conditional edge straight to that node → `END`.
- **2–3 routes** → a `Send()` fan-out to parallel **`contributor`** workers → a **`synthesizer`**
  fan-in node that merges them into one coherent answer → `END`.

There are **8 routes** (`infrastructure/agents/supervisor_route.py`, a `StrEnum`): six market
specialists — **`analyst`**, **`quant`**, **`advisor`**, **`consequence`**, **`macro`**,
**`sentiment`** — plus two scope terminals **`smalltalk`** and **`out_of_scope`** (built cheaper,
without boilerplate, on the `scope_model`).

- **State**: `SupervisorState` (`infrastructure/agents/supervisor_state.py`) —
  `langgraph.graph.MessagesState` (`{"messages": Annotated[list, add_messages]}`) plus
  `routes: list[str]`, `contributor_route: str`, `contributions: Annotated[list[Contribution],
  add]` (an **additive** reducer, so the parallel contributors can each append without clobbering
  one another), `grounding_context`, and `locale`. The supervisor node writes `routes`;
  `select_specialist_routes` (`infrastructure/agents/select_specialist_routes.py`) reads it to
  return either a single edge or the `Send()` fan-out.
- **Supervisor node** (`infrastructure/agents/supervisor_router_node.build_supervisor_router_node`):
  calls `model.with_structured_output(RouteDecision)` (`infrastructure/agents/route_decision.py`
  — `{routes: list[SupervisorRoute] (1..3, unique), reason: str}`, with a validator forbidding a
  scope route from combining with specialists) to pick the routes. The fallback fake chat model
  (no `OPENAI_API_KEY`, see below) can't do structured output, so it's caught and defaulted to a
  single `SupervisorRoute.ADVISOR` route with detail `"fallback routing (no API key)"`, so routing
  degrades gracefully instead of crashing.
- **Specialist nodes** (`infrastructure/agents/specialist_node_factory.build_specialist_node`):
  one factory shared by all six — only `agent_name`, `persona`, and the bound tool subset differ.
  Each persona is a module-level string constant in its own file under
  `infrastructure/agents/personas/`, re-exported from `personas/__init__.py`. The node prepends the
  persona as a `SystemMessage` for that one turn only (never returned in state) and returns just
  the new `AIMessage`. When a node has tools bound it runs a **hand-rolled ReAct loop**
  (`invoke_with_bound_tools.py`, capped at `_MAX_TOOL_ITERATIONS = 3`, each round's tool calls run
  concurrently via `asyncio.gather`) — there is no `ToolNode` or conditional tool edge.
- **Parallel path**: `contributor_node.py` runs one specialist as a hidden "evidence contributor"
  (its tokens are tagged `INTERNAL_CONTRIBUTOR_TAG` so they don't stream to the user) and appends a
  typed `Contribution`; `synthesizer_node.py` fans them in, writes the final answer, and emits the
  `contributions`/`citations` frames that drive the frontend Boardroom + verdict meter.
- **Routes** live in `SupervisorRoute` (`infrastructure/agents/supervisor_route.py`, a `StrEnum`:
  the six specialists above plus `smalltalk` / `out_of_scope`).

**To add a new specialist:** add a value to `SupervisorRoute`, add a persona file under
`personas/`, register the node + its `graph.add_edge(<route>, END)` in
`supervisor_graph.build_supervisor_graph`, add the route to the conditional-edge mapping, and — if
it should join multi-route turns — make sure `select_specialist_routes` and the contributor path
handle it. Bind its tools in `Container._get_chat_graph()`.

`chat_graph.build_chat_graph` (the original single-node graph) still exists but is no longer wired
into `Container` — kept only as a minimal reference shape. A separate **linear** Scenario Lab graph
(`infrastructure/agents/scenario/scenario_graph.py`: `intake → context → causal_chain → quant →
agent_panel → synthesis → compliance → END`, compiled without a checkpointer) is exposed to chat as
the `run_scenario_simulation` tool.

### Locale: two channels, one value (issue #67)

The reply's locale is resolved **once per request**, before the stream opens
(`application/profile/use_cases/resolve_locale.py`: request locale → the user's stored
`preferred_locale` → `Settings.default_locale`), and `LangGraphAgentRunner.stream` then sends it
down **two** channels — because the graph has two kinds of consumer and they can't read the same
one:

| Consumer | Channel | Reads it via |
|----------|---------|--------------|
| supervisor + specialist **nodes** | `SupervisorState["locale"]` | they already take `state` |
| **tools** | the run's `config["configurable"]["locale"]` (`LOCALE_CONFIG_KEY`) | `tools/resolve_tool_locale.py` |

A tool is invoked by `invoke_with_bound_tools` from *inside* a node, so it never receives the
graph state — the config is the only channel that reaches it. Same value, one resolution, so the
two can't disagree.

**When you add a tool that produces LLM-written prose** (a thesis, a rationale, a narrative — as
opposed to raw numbers or verbatim source headlines), wire the locale like this:

```python
async def _run(symbol: str, config: RunnableConfig) -> str:          # `config` is INJECTED
    locale = resolve_tool_locale(config, default_locale)             # turn's locale, else fallback
    result = await use_case.execute(symbol, locale)
```

- Annotating the parameter `RunnableConfig` makes LangChain inject the ambient config **and keep
  the parameter out of the tool's args schema** — so the model never sees it and can't pick a
  language itself. Don't add `locale` as a normal tool argument.
- Keep `default_locale` as the constructor-injected **fallback**, not the operating locale: it's
  what applies where there is no per-turn locale to read (the Telegram and scheduled paths, and
  direct calls outside a graph run).
- Do **not** capture `default_locale` and pass it straight to the use case. That's the bug this
  design replaced: the tools were frozen to the container's default at build time, so a Spanish
  user's chat-initiated signal/sentiment/scenario was generated in — and, for the cached ones,
  *stored under* — the server default.

Note the locale instruction (`application/common/build_locale_instruction.py`) is also
**re-asserted after tool results** in `invoke_with_bound_tools`: tool output is English-heavy and
lands in the recency slot, so the rule has to sit below it, not just in the system block.

### Trace events

Every node emits `AgentTrace` frames via LangGraph's `get_stream_writer()`
(`from langgraph.config import get_stream_writer`), passing a plain dict shaped
`{"agent": str, "event": "routing" | "start" | "done", "detail": str | None}`:
- supervisor emits one `ROUTING` trace (with the chosen route as `detail`);
- each specialist emits `START` before its `model.ainvoke(...)` and `DONE` after.

`AgentTraceEvent` (`domain/agents/entities/agent_trace_event.py`) is the pure `StrEnum` for
these three values; `AgentTrace` (`domain/agents/entities/agent_trace.py`) is the pure entity
`{agent, event, detail}`. Both are domain — no vendor import needed to model them.

Nodes and tools also push **non-trace** payloads over the same `get_stream_writer()` — dicts keyed
`kind: "chart" | "citations" | "contributions" | "tool"` — which the runner turns into `ChartEvent`
/ `CitationsEvent` / `ContributionsEvent` / `ToolCallEvent` (see the SSE section).

### Runner: consuming two stream modes at once

- **`AgentRunner`** (`domain/agents/ports/agent_runner.py`) is the port; **
  `LangGraphAgentRunner`** (`infrastructure/agents/langgraph_agent_runner.py`) is its only
  adapter. `LangGraphAgentRunner.stream(thread_id, message)` runs `graph.astream(...,
  config={"configurable": {"thread_id": thread_id}}, stream_mode=["messages", "custom"])`.
  **Passing a list of stream modes changes the yielded shape**: instead of the bare per-mode
  payload, LangGraph yields `(mode, payload)` tuples —
  - `mode == "messages"`: `payload` is the same `(message_chunk, metadata)` tuple as the
    single-mode case; the adapter extracts `AIMessageChunk.content` (see
    `extract_ai_message_token.py`) and skips everything else.
  - `mode == "custom"`: `payload` is exactly the dict a node or tool passed to
    `get_stream_writer()(...)`, untouched by LangGraph — dispatched by its `kind` into a domain
    `TraceEvent`, `ToolCallEvent`, `ChartEvent`, `CitationsEvent`, or `ContributionsEvent`.
- The adapter yields typed **`AgentStreamEvent`**s (`domain/agents/entities/agent_stream_event.py`
  — a union of `TokenEvent | TraceEvent | ToolCallEvent | ChartEvent | CitationsEvent |
  ContributionsEvent | ErrorEvent`, one dataclass per file) instead of raw strings, so the domain
  layer stays pure while still describing every SSE frame kind.
  **Any exception during the run is caught and yielded as a single `ErrorEvent`** instead of
  propagating — a mid-stream failure still reaches the client as a well-formed frame instead of
  dropping the connection.
- **Per-thread history is the checkpointer's job**, not the application layer's: the
  `AgentMemory` port (`Container.get_agent_memory()`) supplies the checkpointer, which
  persists/replays each thread's accumulated `messages` list keyed by `thread_id`. The
  primary durable adapter is `PostgresCheckpointer` (LangGraph's `AsyncPostgresSaver`,
  built at startup by `initialize_agent_memory()`); it's the only one whose async
  `aget_tuple`/`aput` the `astream` runner can actually await. `RedisCheckpointer` is a
  LEGACY path (the sync `RedisSaver` leaves those async methods unimplemented, so it errors
  on module-capable Redis), and `InMemoryCheckpointer` is the dev/offline fallback. `StreamReply.execute(thread_id, message)` only forwards a single new
  `Message` and passes `AgentStreamEvent`s straight through — it does not build or persist a
  message list itself, so multi-turn conversations aren't amnesiac between calls with the same
  `thread_id`.
- **The models** come from `infrastructure/llm/chat_model_factory.build_chat_model` — see "Swap
  the LLM provider used by agent graphs" above for how to change them. There are **two** cached
  chat models: the router/scope model (`openai_model`, `temperature=router_temperature` = 0.0) and
  the specialist model (`reasoning_model`, which falls back to `openai_model` until
  `OPENAI_MODEL_REASONING` is set). Specialists differ only by persona + bound tool subset.
- **Container caching**: `Container` (`core/di/container.py`) lazily builds and caches each
  adapter (including the chat model, compiled graph, and `AgentRunner`) on first access, so
  they're process-wide singletons — don't reintroduce a "build a new one every call" pattern
  when adding new `get_*`/`_get_*` methods. `Container._get_chat_graph()` now builds the
  Supervisor graph (`build_supervisor_graph`), not `build_chat_graph`.

### SSE wire format (protocol v2)

Each frame is JSON-encoded, not a raw token, and is one of these shapes (the
`tool`/`chart`/`citations`/`contributions` frames were added after the original v2 four):

```
data: {"t": "<token>"}\n\n
data: {"trace": {"agent": "<name>", "event": "routing"|"start"|"done", "detail": "<optional text>"}}\n\n
data: {"tool": {"agent": "<name>", "name": "<tool>", "event": "start"|"done"}}\n\n
data: {"chart": { ...ChartSpec wire dict... }}\n\n
data: {"citations": [ ... ]}\n\n
data: {"contributions": [{"agent": "...", "stance": "...", "confidence": 0.0, "headline": "..."}]}\n\n
data: {"error": "<message>"}\n\n
data: {"done": true}\n\n
```

`api/v1/routers/chat.py`'s `_to_sse_frame` maps each `AgentStreamEvent` variant to exactly one
of these (`detail` is omitted from the trace object when `None`, never sent as `null`), and
`_to_sse` always appends a final `{"done": true}` frame — even after an `{"error": ...}` frame —
so clients can rely on `done` to know the stream is over either way. This is deliberate: a raw
`data: <token>\n\n` frame breaks if a token itself contains a newline, corrupting SSE framing.
The Angular frontend (`SseChatRepository`) reads this with `fetch` + `ReadableStream`, not
`EventSource` (so it can send a POST body), parses each `data:` line as JSON, and maps it to a
`ChatStreamEvent` (`kind: 'token' | 'trace' | 'tool' | 'chart' | 'citations' | 'contributions' | 'error'`).
Keep new streaming endpoints in this same
JSON frame shape unless there's a strong reason to change it.

## Team & ownership

Shared engineering rules live in the root repo's `CLAUDE.md` — everyone follows the same
conventions (Conventional Commits in English, no hardcoded values, one class/function per file,
direct-to-main in pairs, keep CI green). Backend is led by Miquel, with Bryan on the AI/agent layer;
Marco assists with data engineering as a cross-functional floater. See `CODEOWNERS`.

| Dev | Primary area | GitHub |
|-----|--------------|--------|
| Bryan | AI agent dev & project coordination | `@StevSant` |
| Miquel | Backend | `@lesquel` |
| Luis Figueroa | Frontend | `@DweskZ` |
| Kevin Alonso | Branding & UI/UX Design | `@Tokioh` |
| Marco Zambrano | Branding & UI/UX Design & Data Engineering support | `@marco-zambrano` |

**Collaboration:** Kevin and Marco alternate between their primary responsibilities and assisting
other areas as needed, based on project priorities and workload.
