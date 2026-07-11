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

Agent graphs (`infrastructure/agents/chat_graph.py`) don't go through `LLMProvider` —
they run on a LangChain `BaseChatModel`, built by `infrastructure/llm/chat_model_factory.
build_chat_model(settings)`. **This factory function is the swap point** for agent-side
providers (OpenAI → Anthropic/Gemini/Ollama/...):

1. Change `build_chat_model` to return a different LangChain chat model (e.g.
   `ChatAnthropic(...)` from `langchain-anthropic`), gated by a `Settings` field if you
   need to pick at runtime.
2. Nothing in `chat_graph.py`, `langgraph_agent_runner.py`, or `api/` needs to change —
   both only depend on LangChain's `BaseChatModel` interface.
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
field must exist in `.env.example` with a placeholder and a short comment. `REDIS_URL`
is optional — leave it unset locally; `Container.get_agent_memory()` falls back to
`InMemoryCheckpointer` automatically when it's not configured.

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

## Agent layer (LangGraph Supervisor) and streaming (SSE v2)

`POST /api/v1/chat/stream` is routed through the agent layer end to end:

```
chat.py router → StreamReply use case → AgentRunner port → LangGraphAgentRunner adapter
                                                              → compiled Supervisor graph
```

### The Supervisor graph

`infrastructure/agents/supervisor_graph.build_supervisor_graph(model, checkpointer)` builds
the default chat graph: one **`supervisor`** router node, then a conditional edge to exactly
one of six specialist nodes (**`analyst`**, **`quant`**, **`advisor`**, **`consequence`**,
**`macro`**, **`sentiment`** — `infrastructure/agents/supervisor_graph.py:67-103`), then `END`.

- **State**: `SupervisorState` (`infrastructure/agents/supervisor_state.py`) —
  `langgraph.graph.MessagesState` (`{"messages": Annotated[list, add_messages]}`) plus a
  `route: NotRequired[str]` key. The supervisor node writes `route`; `select_specialist_route`
  (`infrastructure/agents/select_specialist_route.py`) reads it to pick the conditional edge.
- **Supervisor node** (`infrastructure/agents/supervisor_router_node.build_supervisor_router_node`):
  calls `model.with_structured_output(RouteDecision)` (`infrastructure/agents/route_decision.py`
  — `{route: SupervisorRoute, reason: str}`) to pick one specialist. The fallback fake chat
  model (no `OPENAI_API_KEY`, see below) doesn't implement `bind_tools`, so
  `with_structured_output(...)` raises `NotImplementedError` immediately — caught and defaulted
  to `SupervisorRoute.ADVISOR` with detail `"fallback routing (no API key)"`, so routing degrades
  gracefully instead of crashing.
- **Specialist nodes** (`infrastructure/agents/specialist_node_factory.build_specialist_node`):
  one factory shared by all six — only `agent_name` and `persona` differ. Each persona is a
  module-level string constant in its own file under `infrastructure/agents/personas/`
  (`analyst_persona.py`, `quant_persona.py`, `advisor_persona.py`, `consequence_persona.py`,
  `macro_persona.py`, `sentiment_persona.py`), re-exported from `personas/__init__.py`. The node prepends the persona as a `SystemMessage` for that one
  `model.ainvoke(...)` call only (never returned in state, so it doesn't accumulate across
  turns) and returns just the new `AIMessage` — same "let `add_messages` append it" pattern as
  the old single-node graph.
- **Routes** live in `SupervisorRoute` (`infrastructure/agents/supervisor_route.py:11-16`, a
  `StrEnum`: `analyst` / `quant` / `advisor` / `consequence` / `macro` / `sentiment`).

**To add a new specialist:** add a value to `SupervisorRoute`, add a persona file under
`personas/`, add a `graph.add_node(...)` + `graph.add_edge(<route>, END)` call in
`supervisor_graph.build_supervisor_graph`, and add the route to the conditional-edge mapping.
Nothing else in the codebase needs to change.

`chat_graph.build_chat_graph` (the original single-node graph) still exists but is no longer
wired into `Container` — kept only as a minimal reference shape.

### Trace events

Every node emits `AgentTrace` frames via LangGraph's `get_stream_writer()`
(`from langgraph.config import get_stream_writer`), passing a plain dict shaped
`{"agent": str, "event": "routing" | "start" | "done", "detail": str | None}`:
- supervisor emits one `ROUTING` trace (with the chosen route as `detail`);
- each specialist emits `START` before its `model.ainvoke(...)` and `DONE` after.

`AgentTraceEvent` (`domain/agents/entities/agent_trace_event.py`) is the pure `StrEnum` for
these three values; `AgentTrace` (`domain/agents/entities/agent_trace.py`) is the pure entity
`{agent, event, detail}`. Both are domain — no vendor import needed to model them.

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
  - `mode == "custom"`: `payload` is exactly the dict a node passed to
    `get_stream_writer()(...)`, untouched by LangGraph — turned into a domain `AgentTrace` by
    `build_agent_trace_from_payload.py`.
- The adapter yields typed **`AgentStreamEvent`**s (`domain/agents/entities/agent_stream_event.py`
  — a union of `TokenEvent | TraceEvent | ErrorEvent`, one dataclass per file) instead of raw
  strings, so the domain layer stays pure while still describing every SSE v2 frame kind.
  **Any exception during the run is caught and yielded as a single `ErrorEvent`** instead of
  propagating — a mid-stream failure still reaches the client as a well-formed frame instead of
  dropping the connection.
- **Per-thread history is the checkpointer's job**, not the application layer's: the
  `AgentMemory` port (`Container.get_agent_memory()`, in-memory or Redis) supplies the
  checkpointer, which persists/replays each thread's accumulated `messages` list keyed by
  `thread_id`. `StreamReply.execute(thread_id, message)` only forwards a single new
  `Message` and passes `AgentStreamEvent`s straight through — it does not build or persist a
  message list itself, so multi-turn conversations aren't amnesiac between calls with the same
  `thread_id`.
- **The model itself** comes from `infrastructure/llm/chat_model_factory.build_chat_model`
  — see "Swap the LLM provider used by agent graphs" above for how to change it. The Supervisor
  and all six specialists share this one model instance; only the system prompt differs.
- **Container caching**: `Container` (`core/di/container.py`) lazily builds and caches each
  adapter (including the chat model, compiled graph, and `AgentRunner`) on first access, so
  they're process-wide singletons — don't reintroduce a "build a new one every call" pattern
  when adding new `get_*`/`_get_*` methods. `Container._get_chat_graph()` now builds the
  Supervisor graph (`build_supervisor_graph`), not `build_chat_graph`.

### SSE wire format (protocol v2)

Each frame is JSON-encoded, not a raw token, and is one of exactly four shapes:

```
data: {"t": "<token>"}\n\n
data: {"trace": {"agent": "<name>", "event": "routing"|"start"|"done", "detail": "<optional text>"}}\n\n
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
`ChatStreamEvent` (`{kind: 'token'|'trace'|'error'}`). Keep new streaming endpoints in this same
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
