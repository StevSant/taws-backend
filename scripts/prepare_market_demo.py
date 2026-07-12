"""Warm the live news and signal pipelines before a product demonstration.

Run while the backend is available:

    uv run python scripts/prepare_market_demo.py

The script first ingests recent news through the same endpoint used by Radar, then asks
the existing batch Analyst pipeline to classify every linked pending item. Re-running is
safe: news is deduplicated by URL and already-processed items are not analyzed again.
"""

import argparse
import asyncio

import httpx


async def prepare(base_url: str, limit: int) -> None:
    timeout = httpx.Timeout(180.0)
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        news_response = await client.get(
            "/api/v1/news",
            params={"since_hours": 48, "limit": limit},
        )
        news_response.raise_for_status()
        news = news_response.json()
        print(f"Ingested {len(news.get('items', []))} recent news item(s).")

        analysis_response = await client.post("/api/v1/news/analyze-pending")
        analysis_response.raise_for_status()
        result = analysis_response.json()
        print(
            "Prepared signals: "
            f"{result.get('analyzed_count', 0)} analyzed, "
            f"{result.get('skipped_count', 0)} skipped, "
            f"{result.get('failed_count', 0)} pending retry."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm TAWS news and signals for the demo.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    asyncio.run(prepare(args.base_url, args.limit))


if __name__ == "__main__":
    main()
