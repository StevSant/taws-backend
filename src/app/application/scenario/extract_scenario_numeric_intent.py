import re

from app.domain.scenario.entities import ScenarioDirection

_TARGET_PATTERN = re.compile(
    r"(?:\ba\b|\bhasta\b|\bto\b)\s+(?:los\s+)?(?:usd\s*)?\$?\s*"
    r"(?P<number>\d+(?:[.,]\d+)?)\s*"
    r"(?P<scale>mil|k|millones?|million)?\s*"
    r"(?:d[oó]lares|dollars?|usd)?",
    re.IGNORECASE,
)
_DAYS_PATTERN = re.compile(r"(?:en|within|in)\s+(\d+)\s+d[ií]as?", re.IGNORECASE)
_DOWN_WORDS = re.compile(r"\b(cae|caiga|baja|baje|pierde|falls?|drops?|declines?)\b", re.IGNORECASE)
_UP_WORDS = re.compile(r"\b(sube|suba|aumenta|rises?|gains?|climbs?)\b", re.IGNORECASE)


def extract_scenario_numeric_intent(
    text: str,
) -> tuple[float | None, ScenarioDirection | None, int | None]:
    """Deterministically preserve price and timing phrases the LLM may omit."""

    target_price = _extract_target_price(text)
    direction = _extract_direction(text)
    timeframe_days = _extract_timeframe_days(text)
    return target_price, direction, timeframe_days


def _extract_target_price(text: str) -> float | None:
    match = _TARGET_PATTERN.search(text)
    if match is None:
        return None
    number = _parse_number(match.group("number"))
    scale = (match.group("scale") or "").lower()
    if scale in {"mil", "k"}:
        number *= 1_000
    elif scale in {"millon", "millones", "million"}:
        number *= 1_000_000
    return number if number > 0 else None


def _parse_number(raw: str) -> float:
    separator = "." if "." in raw else "," if "," in raw else None
    if separator is None:
        return float(raw)
    whole, fractional = raw.rsplit(separator, 1)
    if len(fractional) == 3:
        return float(whole + fractional)
    return float(f"{whole}.{fractional}")


def _extract_direction(text: str) -> ScenarioDirection | None:
    if _DOWN_WORDS.search(text):
        return ScenarioDirection.DOWN
    if _UP_WORDS.search(text):
        return ScenarioDirection.UP
    return None


def _extract_timeframe_days(text: str) -> int | None:
    lowered = text.lower()
    if "mañana" in lowered or "tomorrow" in lowered:
        return 1
    if "esta semana" in lowered or "this week" in lowered:
        return 7
    if "este mes" in lowered or "this month" in lowered:
        return 30
    match = _DAYS_PATTERN.search(text)
    return int(match.group(1)) if match is not None else None
