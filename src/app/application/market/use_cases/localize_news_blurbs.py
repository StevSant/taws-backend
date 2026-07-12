from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from app.application.common import build_locale_instruction
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_ITEMS = 12
_MAX_BLURB_CHARS = 220

_SYSTEM_PROMPT = (
    "You write tiny news blurbs for a market radar UI. "
    "For each article, produce ONE short sentence (max 30 words) that captures the gist. "
    "Keep tickers and company names. Do not add opinions, advice, or extra commentary."
)

_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "blurb": {"type": "string"},
                },
                "required": ["id", "blurb"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class NewsBlurbSource:
    id: str
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class NewsBlurb:
    id: str
    blurb: str


class LocalizeNewsBlurbs:
    """Translate/summarize news headlines into short locale-aware blurbs for the timeline.

    In-memory cache so repeated Radar loads do not re-spend LLM tokens. Degrades to a
    cleaned/truncated source summary when the LLM call fails.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider
        self._cache: dict[str, str] = {}

    async def execute(self, items: list[NewsBlurbSource], locale: str) -> list[NewsBlurb]:
        locale_key = (locale or "es").strip().lower() or "es"
        capped = items[:_MAX_ITEMS]
        if not capped:
            return []

        result: list[NewsBlurb] = []
        missing: list[NewsBlurbSource] = []

        for item in capped:
            cache_key = self._cache_key(locale_key, item)
            cached = self._cache.get(cache_key)
            if cached:
                result.append(NewsBlurb(id=item.id, blurb=cached))
            else:
                missing.append(item)

        if missing:
            generated = await self._generate(missing, locale_key)
            by_id = {row.id: row.blurb for row in generated}
            for item in missing:
                blurb = by_id.get(item.id) or self._fallback_blurb(item)
                self._cache[self._cache_key(locale_key, item)] = blurb
                result.append(NewsBlurb(id=item.id, blurb=blurb))

        order = {item.id: index for index, item in enumerate(capped)}
        result.sort(key=lambda row: order.get(row.id, 0))
        return result

    async def _generate(self, items: list[NewsBlurbSource], locale: str) -> list[NewsBlurb]:
        lines = []
        for item in items:
            summary = _clean_text(item.summary)
            lines.append(
                f"- id={item.id}\n  title={item.title.strip()}\n  summary={summary or '(none)'}"
            )
        user_content = (
            "Return JSON with one blurb per id.\n\nArticles:\n" + "\n".join(lines)
        )
        try:
            payload = await self._llm.complete_structured(
                [
                    Message(
                        role=MessageRole.SYSTEM,
                        content=_SYSTEM_PROMPT + build_locale_instruction(locale),
                    ),
                    Message(role=MessageRole.USER, content=user_content),
                ],
                schema=_RESPONSE_SCHEMA,
                schema_name="news_blurbs",
            )
        except Exception:
            logger.exception("Failed to localize news blurbs for locale=%s", locale)
            return []

        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return []

        blurbs: list[NewsBlurb] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            news_id = str(row.get("id") or "").strip()
            blurb = _clean_text(str(row.get("blurb") or ""))
            if not news_id or not blurb:
                continue
            blurbs.append(NewsBlurb(id=news_id, blurb=blurb[:_MAX_BLURB_CHARS]))
        return blurbs

    def _fallback_blurb(self, item: NewsBlurbSource) -> str:
        text = _clean_text(item.summary) or _clean_text(item.title)
        if len(text) <= _MAX_BLURB_CHARS:
            return text
        return text[: _MAX_BLURB_CHARS - 1].rstrip() + "…"

    @staticmethod
    def _cache_key(locale: str, item: NewsBlurbSource) -> str:
        digest = hashlib.sha1(f"{item.title}\n{item.summary}".encode("utf-8")).hexdigest()[:10]
        return f"{locale}:{item.id}:{digest}"


def _clean_text(value: str) -> str:
    without_tags = _HTML_TAG_RE.sub(" ", value or "")
    return _WHITESPACE_RE.sub(" ", without_tags).strip()
