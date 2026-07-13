import logging
import time
from typing import Any

import httpx

from app.domain.market.entities import InstrumentMetadata
from app.domain.market.ports import InstrumentMetadataProvider

logger = logging.getLogger(__name__)


class CoinGeckoInstrumentMetadataProvider(InstrumentMetadataProvider):
    """InstrumentMetadataProvider adapter backed by CoinGecko's `/coins/markets`.

    Makes ONE batch call per `get_metadata_batch(symbols)` invocation (design
    decision #2) — never one request per symbol. `coingecko_id_overrides` maps a
    domain symbol to its CoinGecko coin id, resolved the SAME way
    `CoinGeckoMarketDataProvider` resolves price-series ids: from the instrument
    universe's live override dict (`SupabaseInstrumentUniverse.
    coingecko_id_overrides()`), never a lowercase guess — a stock symbol with no
    override entry never reaches CoinGecko and is simply absent from the result.

    Reuses the exact cooldown/circuit-breaker shape as
    `CoinGeckoMarketDataProvider`/`CoinGeckoCoinSearchProvider`: once a live call
    fails (rate-limited or unreachable, including a malformed 200 body), back off
    for `cooldown_seconds` and return `{}` on every subsequent call instead of
    hammering CoinGecko — this is the enrichment spec's "CoinGecko is fully
    unavailable" degrade-to-null contract at the provider boundary. Symbols
    CoinGecko simply omits from its response (delisted coin, etc.) are likewise
    left out of the returned dict; the caller (`ListEnrichedInstruments`) maps
    every absent key onto `InstrumentMetadata(None, None, None)`.
    """

    def __init__(
        self,
        base_url: str,
        coingecko_id_overrides: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        api_key: str | None = None,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._base_url = base_url
        self._overrides = coingecko_id_overrides or {}
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key or None
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float | None = None

    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        symbol_by_coin_id = {
            self._overrides[symbol]: symbol for symbol in symbols if symbol in self._overrides
        }
        if not symbol_by_coin_id:
            return {}
        if self._in_cooldown():
            return {}

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds, headers=self._headers()
            ) as client:
                response = await client.get(
                    "/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "ids": ",".join(symbol_by_coin_id.keys()),
                        "price_change_percentage": "7d",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            return _to_metadata_by_symbol(payload, symbol_by_coin_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            # `ValueError` covers `json.JSONDecodeError` (malformed body on a 200);
            # `KeyError`/`TypeError`/`AttributeError` cover an unexpected row shape.
            self._enter_cooldown(error)
            return {}

    def _headers(self) -> dict[str, str]:
        return {"x-cg-demo-api-key": self._api_key} if self._api_key else {}

    def _in_cooldown(self) -> bool:
        if self._cooldown_until is None:
            return False
        if time.monotonic() >= self._cooldown_until:
            self._cooldown_until = None
            return False
        return True

    def _enter_cooldown(self, error: Exception) -> None:
        self._cooldown_until = time.monotonic() + self._cooldown_seconds
        logger.warning(
            "CoinGecko markets metadata unavailable (%s); backing off for %.0fs and "
            "returning no metadata.",
            error,
            self._cooldown_seconds,
        )


def _to_metadata_by_symbol(
    payload: Any, symbol_by_coin_id: dict[str, str]
) -> dict[str, InstrumentMetadata]:
    """Map `/coins/markets` rows onto `{domain_symbol: InstrumentMetadata}`.

    Rows CoinGecko didn't return for a requested id (delisted coin, etc.) are
    simply absent from `symbol_by_coin_id` lookups and thus omitted here too.
    """
    result: dict[str, InstrumentMetadata] = {}
    for row in payload:
        coin_id = row["id"]
        symbol = symbol_by_coin_id.get(coin_id)
        if symbol is None:
            continue
        result[symbol] = InstrumentMetadata(
            market_cap=row.get("market_cap"),
            volume_24h=row.get("total_volume"),
            change_7d_pct=row.get("price_change_percentage_7d_in_currency"),
        )
    return result
