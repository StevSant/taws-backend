from typing import Any

from app.domain.agents.ports import AgentMemory

# Small, fixed pool — this is the agent checkpointer for a single long-lived server
# process, not a general query pool. `min_size=1` keeps one warm connection so the first
# chat turn after boot doesn't pay a connect; `max_size=4` allows a little concurrency so a
# slow checkpoint write doesn't serialize every in-flight chat on one connection.
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 4

_NOT_INITIALIZED_ERROR = (
    "[PostgresCheckpointer] get_checkpointer() called before initialize(). Await "
    "initialize() once during app startup before wiring the checkpointer into the graph."
)


class PostgresCheckpointer(AgentMemory):
    """AgentMemory adapter backed by Postgres via LangGraph's `AsyncPostgresSaver`.

    This is the primary DURABLE agent checkpointer. Unlike the sync `RedisSaver`
    (`RedisCheckpointer`), `AsyncPostgresSaver` implements the async checkpoint methods
    (`aget_tuple`/`aput`/...) that `graph.astream(...)` awaits on the chat path — so it
    actually works under the async runner, which the sync Redis saver does not.

    Built async, not lazily: `initialize()` opens an `AsyncConnectionPool` and awaits the
    saver's `setup()` (which creates the checkpoint tables and runs the library's own
    migrations) exactly once at app startup. `get_checkpointer()` then only returns the
    already-built saver — it never constructs one on the request path, and raises if called
    before `initialize()`.

    **Why a pool, not a single connection.** The saver accepts either an `AsyncConnection`
    or an `AsyncConnectionPool`. A single long-lived connection is a single point of
    failure for a persistent server: Supabase's pooler or Postgres' idle timeout can drop
    it, after which every checkpoint op fails for the rest of the process with no recovery.
    A pool (with `check=AsyncConnectionPool.check_connection`) detects and replaces dead
    connections transparently, and lets a few checkpoint ops run concurrently instead of
    serializing the whole app behind one connection. `PgvectorStore`'s open-per-call
    approach doesn't fit here because the checkpointer is constructed once and held for the
    whole process lifetime, on the hot chat path.

    **Connection kwargs mirror the library's own `from_conn_string`:** `autocommit=True`
    (the saver issues DDL/writes without wrapping them in an explicit transaction, so they
    must auto-commit), `prepare_threshold=0` (disables server-side prepared statements, so
    the saver stays compatible with Supabase's transaction-mode pooler / PgBouncer), and
    `row_factory=dict_row` (the saver reads rows by column name).

    **Schema ownership.** The checkpoint tables (`checkpoints`, `checkpoint_writes`,
    `checkpoint_blobs`, `checkpoint_migrations`) are created and versioned by the saver's
    own `setup()`, deliberately OUTSIDE Alembic. That's accepted, not an oversight:
    hand-porting the library's private DDL into our migrations would couple our schema
    history to `langgraph-checkpoint-postgres`'s internals and break on every upgrade.
    `setup()` is idempotent (it tracks its version in `checkpoint_migrations`), so running
    it on every boot is safe.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: Any | None = None
        self._saver: Any | None = None

    async def initialize(self) -> None:
        """Open the connection pool, build the saver, and run its one-time `setup()`.

        Idempotent-friendly: safe to call once at startup. Raises if the database is
        unreachable or `setup()` fails — the DI container catches that and decides whether
        to degrade to in-memory (see `Container.initialize_agent_memory`).
        """
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=self._database_url,
            min_size=_POOL_MIN_SIZE,
            max_size=_POOL_MAX_SIZE,
            open=False,
            check=AsyncConnectionPool.check_connection,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await pool.open(wait=True)
        try:
            # psycopg_pool types the pool's connection generic invariantly, so pyright can't
            # see this as `AsyncConnectionPool[AsyncConnection[DictRow]]` even though the
            # kwargs make it exactly that; the saver accepts the pool fine at runtime.
            saver = AsyncPostgresSaver(conn=pool)  # type: ignore[arg-type]
            await saver.setup()
        except Exception:
            await pool.close()
            raise
        self._pool = pool
        self._saver = saver

    def get_checkpointer(self) -> Any:
        if self._saver is None:
            raise RuntimeError(_NOT_INITIALIZED_ERROR)
        return self._saver

    async def aclose(self) -> None:
        """Close the connection pool on shutdown. Safe to call if never initialized."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._saver = None
