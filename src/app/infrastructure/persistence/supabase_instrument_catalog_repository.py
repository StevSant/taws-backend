from functools import partial
from typing import Any

from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import InstrumentCatalogRepository
from app.infrastructure.persistence.supabase_client_cache import SupabaseClientCache
from app.infrastructure.persistence.with_supabase_retry import with_supabase_retry

_INSTRUMENTS_TABLE = "instruments"


def _instrument_row_from_row(row: Any) -> InstrumentRow:
    """Map one `instruments` table row (as returned by `supabase-py`) onto `InstrumentRow`.

    Typed `Any` for the same reason as `watchlist_from_row`: `postgrest`'s response
    rows are typed as the broad `JSON` union, which pyright won't narrow to `dict`.
    """
    return InstrumentRow(
        symbol=row["symbol"],
        name=row["name"],
        asset_class=AssetClass(row["asset_class"]),
        currency=row["currency"],
        coingecko_id=row.get("coingecko_id"),
        yfinance_symbol=row.get("yfinance_symbol"),
    )


class SupabaseInstrumentCatalogRepository(InstrumentCatalogRepository):
    """InstrumentCatalogRepository adapter backed by Supabase Postgres via `supabase-py`.

    See `backend/migrations/versions/0012_instruments.py` for the schema
    (`public.instruments`) and its RLS policy (read-only for `authenticated`;
    writes only succeed via the service-role key, same pattern as `signals`).

    Every `.execute()` call is wrapped in `with_supabase_retry` (issue #7) — see
    `SupabaseWatchlistRepository`'s docstring for the shared rationale.
    """

    def __init__(
        self,
        supabase_url: str | None,
        supabase_key: str | None,
        retry_max_attempts: int = 2,
        retry_backoff_base_seconds: float = 0.2,
    ) -> None:
        self._clients = SupabaseClientCache(supabase_url, supabase_key)
        self._retry = partial(
            with_supabase_retry,
            max_attempts=retry_max_attempts,
            backoff_base_seconds=retry_backoff_base_seconds,
        )

    async def upsert(self, row: InstrumentRow) -> None:
        client = await self._clients.get()
        await self._retry(
            lambda: (
                client.table(_INSTRUMENTS_TABLE)
                .upsert(
                    {
                        "symbol": row.symbol,
                        "name": row.name,
                        "asset_class": row.asset_class.value,
                        "currency": row.currency,
                        "coingecko_id": row.coingecko_id,
                        "yfinance_symbol": row.yfinance_symbol,
                    },
                    on_conflict="symbol",
                    ignore_duplicates=True,
                )
                .execute()
            )
        )

    async def all_rows(self) -> list[InstrumentRow]:
        client = await self._clients.get()
        response = await self._retry(lambda: client.table(_INSTRUMENTS_TABLE).select("*").execute())
        return [_instrument_row_from_row(row) for row in response.data]
