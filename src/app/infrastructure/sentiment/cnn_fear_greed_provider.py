from datetime import UTC, datetime
from typing import Any

import httpx

from app.domain.sentiment.entities import FearGreedReading
from app.infrastructure.sentiment.parse_fear_greed_classification import (
    parse_fear_greed_classification,
)

CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class CnnFearGreedProvider:
    """Stock-market Fear & Greed Index via CNN's public graphdata API."""

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def get_fear_greed_index(self) -> FearGreedReading:
        reading, _delta = await self.fetch_snapshot()
        return reading

    async def fetch_snapshot(self) -> tuple[FearGreedReading, float]:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(
                CNN_FEAR_GREED_URL,
                headers={"User-Agent": CNN_USER_AGENT, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()

        return _to_reading(payload)


def _to_reading(payload: dict[str, Any]) -> tuple[FearGreedReading, float]:
    block = payload.get("fear_and_greed") or {}
    score = block.get("score")
    if score is None:
        raise RuntimeError("[CnnFearGreedProvider] CNN response missing fear_and_greed.score")

    rating = block.get("rating") or "neutral"
    previous = block.get("previous_close")
    delta = float(score) - float(previous) if previous is not None else 0.0

    timestamp_raw = block.get("timestamp")
    as_of = _parse_timestamp(timestamp_raw)

    return (
        FearGreedReading(
            value=int(round(float(score))),
            classification=parse_fear_greed_classification(str(rating)),
            as_of=as_of,
        ),
        round(delta, 1),
    )


def _parse_timestamp(raw: Any) -> datetime:
    if isinstance(raw, str) and raw.strip():
        normalized = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return datetime.now(tz=UTC)
