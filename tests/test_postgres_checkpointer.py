"""`PostgresCheckpointer` + `Container` agent-memory wiring — fully offline (no real DB).

Covers the two behaviors that guard the checkpointer defect fix:
- `get_checkpointer()` refuses to hand back a saver before `initialize()` ran.
- `Container.initialize_agent_memory()` prefers the durable Postgres checkpointer when
  `DATABASE_URL` is set, and degrades to `InMemoryCheckpointer` (never crashes) when the
  Postgres checkpointer fails to initialize.

`PostgresCheckpointer.initialize()` is monkeypatched at the class level so no connection is
ever opened — `PostgresCheckpointer.__init__` itself does no I/O, so constructing one is safe.
"""

from typing import Any

import pytest

from app.core.config import Settings
from app.core.di import Container
from app.infrastructure.memory import InMemoryCheckpointer, PostgresCheckpointer


def test_get_checkpointer_raises_before_initialize() -> None:
    checkpointer = PostgresCheckpointer(database_url="postgresql://user:pass@host:5432/db")

    with pytest.raises(RuntimeError):
        checkpointer.get_checkpointer()


async def test_initialize_agent_memory_uses_postgres_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_saver = object()

    async def _fake_initialize(self: PostgresCheckpointer) -> None:
        self._saver = sentinel_saver  # pretend setup() succeeded

    monkeypatch.setattr(PostgresCheckpointer, "initialize", _fake_initialize)
    container = Container(settings=Settings(app_env="production", database_url="postgresql://x/db"))

    await container.initialize_agent_memory()

    memory = container.get_agent_memory()
    assert isinstance(memory, PostgresCheckpointer)
    assert memory.get_checkpointer() is sentinel_saver


async def test_initialize_agent_memory_degrades_to_in_memory_when_postgres_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: PostgresCheckpointer) -> None:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(PostgresCheckpointer, "initialize", _boom)
    container = Container(settings=Settings(app_env="production", database_url="postgresql://x/db"))

    await container.initialize_agent_memory()  # must NOT raise — degrade, don't crash boot

    assert isinstance(container.get_agent_memory(), InMemoryCheckpointer)


async def test_aclose_agent_memory_noops_without_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(self: PostgresCheckpointer) -> None:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(PostgresCheckpointer, "initialize", _boom)
    container = Container(settings=Settings(app_env="production", database_url="postgresql://x/db"))
    await container.initialize_agent_memory()

    # Fell back to InMemoryCheckpointer, which holds no pool — aclose must be a safe no-op.
    await container.aclose_agent_memory()


async def test_aclose_agent_memory_closes_postgres_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: dict[str, bool] = {"value": False}

    async def _fake_initialize(self: PostgresCheckpointer) -> None:
        self._saver = object()

    async def _fake_aclose(self: PostgresCheckpointer) -> None:
        closed["value"] = True

    monkeypatch.setattr(PostgresCheckpointer, "initialize", _fake_initialize)
    monkeypatch.setattr(PostgresCheckpointer, "aclose", _fake_aclose)
    container = Container(settings=Settings(app_env="production", database_url="postgresql://x/db"))
    await container.initialize_agent_memory()

    await container.aclose_agent_memory()

    assert closed["value"] is True


def test_get_agent_memory_falls_back_to_in_memory_in_dev_without_lifespan() -> None:
    # A code path that never ran `initialize_agent_memory` (unit tests, direct construction)
    # keeps the legacy synchronous selection: dev + no REDIS_URL -> in-memory.
    container = Container(settings=Settings(app_env="development", redis_url=None))

    memory: Any = container.get_agent_memory()

    assert isinstance(memory, InMemoryCheckpointer)
