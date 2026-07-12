import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# Only DNS/connectivity-level failures are transient enough to be worth retrying — a
# fresh attempt a few hundred ms later has a real chance of hitting a resolved DNS
# cache or a recovered connection. Application-level Postgrest errors (RLS violations,
# constraint errors, malformed queries — anything the `supabase-py` client raises as
# `postgrest.PostgrestAPIError`) are NOT included here on purpose: retrying those would
# never succeed and would only add latency before the identical error surfaces anyway.
_TRANSIENT_NETWORK_ERRORS: tuple[type[Exception], ...] = (httpx.ConnectError, httpx.ReadTimeout)


async def with_supabase_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    backoff_base_seconds: float,
) -> T:
    """Run a Supabase client call, retrying only transient network failures.

    Used by every `Supabase*Repository` adapter to wrap each `client.table(...)
    .execute()` call (issue #7) — a single shared helper so retry behavior stays
    consistent across all of them instead of being reimplemented per class.

    Retries `httpx.ConnectError` / `httpx.ReadTimeout` up to `max_attempts` times with
    short exponential backoff (`backoff_base_seconds * 2**attempt`). Any other
    exception propagates immediately on first failure — see the module docstring
    comment above for why that includes Postgrest's own 4xx errors.
    """
    attempt = 0
    while True:
        try:
            return await operation()
        except _TRANSIENT_NETWORK_ERRORS as exc:
            attempt += 1
            if attempt > max_attempts:
                logger.warning(
                    "Supabase call failed after %d retries with a transient network "
                    "error; giving up: %s",
                    max_attempts,
                    exc,
                )
                raise
            delay = backoff_base_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Transient Supabase network error (attempt %d/%d); retrying in %.2fs: %s",
                attempt,
                max_attempts,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
