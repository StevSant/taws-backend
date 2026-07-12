import html

from app.domain.scenario.entities import ScenarioResult
from app.infrastructure.telegram.truncate_telegram_text import truncate_telegram_text

_MAX_ASSET_CLASS_IMPACTS = 2


def format_scenario_result_reply(result: ScenarioResult, frontend_base_url: str) -> str:
    header = f"🎲 <b>Scenario — {html.escape(result.title)}</b>"
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
    body_parts = [
        header,
        "\n━━━━━━━━━━━━━━━━━━",
    ]
    if impact_lines:
        body_parts.append(f"📊 <b>Key Impacts</b>\n{impact_lines}")
    body_parts.append(f"🔗 <a href='{link}'>View full results</a>")
    body_parts.append(f"\n━━━━━━━━━━━━━━━━━━\n{disclaimer}")
    return truncate_telegram_text("\n\n".join(body_parts))
