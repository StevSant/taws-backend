import html

from app.domain.scenario.entities import ScenarioResult
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_MAX_ASSET_CLASS_IMPACTS = 2


def format_scenario_result_reply(result: ScenarioResult, frontend_base_url: str) -> str:
    """Render a CONDENSED, Telegram-friendly (HTML `parse_mode`) reply for `/simular
    <text>`'s follow-up delivery (issue #19): the scenario title, the top
    `_MAX_ASSET_CLASS_IMPACTS` asset-class impacts by confidence, a link back to the
    full result in the app, and the compliance disclaimer.

    Deliberately NOT the full narrative/impact map/recommended-actions dump
    `run_scenario_simulation_tool._format_result` builds for chat — this reply is sent
    on a slow follow-up message, after the fast ack, and issue #19 explicitly asks for
    "title + top 1-2 asset-class impacts + a link back to the app for the full result."
    """
    header = f"<b>{html.escape(result.title)}</b>"
    top_impacts = sorted(result.impact_map, key=lambda impact: impact.confidence, reverse=True)[
        :_MAX_ASSET_CLASS_IMPACTS
    ]
    impact_lines = "\n".join(
        f"• {html.escape(impact.asset_class.value)}: {impact.direction.value} "
        f"(confidence {impact.confidence:.0%})"
        for impact in top_impacts
    )
    link = f"{frontend_base_url.rstrip('/')}/scenarios/{result.id}"
    disclaimer = html.escape(result.disclaimer)
    body_parts = [header]
    if impact_lines:
        body_parts.append(impact_lines)
    body_parts.append(f"Full result: {link}")
    body_parts.append(disclaimer)
    return truncate_telegram_text("\n\n".join(body_parts))
