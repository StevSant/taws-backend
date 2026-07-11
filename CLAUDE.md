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

## Agent layer (LangGraph) and streaming (SSE)

`POST /api/v1/chat/stream` is routed through the agent layer end to end:

```
chat.py router → StreamReply use case → AgentRunner port → LangGraphAgentRunner adapter
                                                              → compiled LangGraph graph
```

- **`AgentRunner`** (`domain/agents/ports/agent_runner.py`) is the port; **
  `LangGraphAgentRunner`** (`infrastructure/agents/langgraph_agent_runner.py`) is its only
  adapter. `LangGraphAgentRunner.stream(thread_id, message)` runs `graph.astream(...,
  config={"configurable": {"thread_id": thread_id}}, stream_mode="messages")`, which
  yields `(message_chunk, metadata)` tuples per LLM token; the adapter extracts
  `AIMessageChunk.content` (see `extract_ai_message_token.py`) and skips everything else.
- **The graph** (`infrastructure/agents/chat_graph.build_chat_graph(model, checkpointer)`)
  is a single-node graph over `langgraph.graph.MessagesState`
  (`{"messages": Annotated[list, add_messages]}`), compiled with `graph.compile(checkpointer=
  checkpointer)`. The node does `await model.ainvoke(state["messages"])` and returns only the
  new `AIMessage` — the `add_messages` reducer appends it to the thread's history instead of
  replacing it.
- **Per-thread history is the checkpointer's job**, not the application layer's: the
  `AgentMemory` port (`Container.get_agent_memory()`, in-memory or Redis) supplies the
  checkpointer, which persists/replays each thread's accumulated `messages` list keyed by
  `thread_id`. `StreamReply.execute(thread_id, message)` only forwards a single new
  `Message` — it does not build or persist a message list itself, so multi-turn
  conversations aren't amnesiac between calls with the same `thread_id`.
- **The model itself** comes from `infrastructure/llm/chat_model_factory.build_chat_model`
  — see "Swap the LLM provider used by agent graphs" above for how to change it.
- **Container caching**: `Container` (`core/di/container.py`) lazily builds and caches each
  adapter (including the chat model, compiled graph, and `AgentRunner`) on first access, so
  they're process-wide singletons — don't reintroduce a "build a new one every call" pattern
  when adding new `get_*`/`_get_*` methods.

SSE wire format: each frame is JSON-encoded, not a raw token —
`data: {"t": "<token>"}\n\n`, ending with `data: {"done": true}\n\n`. This is deliberate:
a raw `data: <token>\n\n` frame breaks if a token itself contains a newline, corrupting SSE
framing. The Angular frontend (`SseChatRepository`) reads this with `fetch` +
`ReadableStream`, not `EventSource` (so it can send a POST body), parses each `data:` line
as JSON, yields `.t`, and stops on `.done`. Keep new streaming endpoints in this same JSON
frame shape unless there's a strong reason to change it.

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
