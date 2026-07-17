import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from app.infrastructure.agents.contribution import Contribution
from app.infrastructure.agents.internal_contributor_tag import INTERNAL_CONTRIBUTOR_TAG

_logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """Extract only claims and evidence explicitly present in the supplied \
specialist response. Never add facts, URLs, dates, identifiers, metrics, or providers. Use \
news for publisher/title/URL/date evidence; signal for stored impact/confidence; quant for \
computed metrics; macro for provider-dated indicators. Omit any finding that cannot fill its \
source schema from the response itself. Also carry through the specialist's own self-reported \
stance (bull, bear, or neutral), confidence (0.0 to 1.0), and short headline when the response \
states them; leave stance at neutral, confidence at 0.0, and headline empty when it does not."""


async def extract_response_contribution(
    model: BaseChatModel,
    agent_name: str,
    response: BaseMessage,
    evidence_messages: list[BaseMessage] | None = None,
) -> Contribution:
    """Turn a completed specialist response into typed, non-user-facing evidence.

    After the LLM extraction, findings are deterministically validated against the tool
    evidence: any finding whose source carries a URL (today only `NewsSource`) is DROPPED
    unless that URL appears verbatim in the concatenated evidence text. This kills the
    failure mode where the extractor emits a plausible-but-fabricated link and it reaches
    the user badged as a verified citation. Findings whose source variant has no URL field
    (signal/quant/macro) are kept as-is — they're grounded by other means.

    `analysis` is always overwritten with the specialist's real response `content` — on both the
    success path and the extraction-failure fallback — never left to whatever the structured-output
    call may have put there. It carries the contributor's full grounded prose through to the
    synthesizer so numbers, caveats, and chart references the typed digest drops aren't lost, and
    so an extraction failure degrades to summary+analysis instead of summary-only. The multi-route
    contributor bounds this field before it enters the synthesis prompt; the single-route path
    discards the digest after citation extraction, so an untruncated value never reaches a model.
    """
    content = str(getattr(response, "content", response))
    try:
        structured_model = model.with_structured_output(Contribution)
        evidence_rule = (
            " Every source field must be copied from the tool evidence messages."
            if evidence_messages
            else ""
        )
        extracted = await structured_model.ainvoke(
            [
                SystemMessage(content=_EXTRACTION_PROMPT + evidence_rule),
                *(evidence_messages or []),
                response,
            ],
            config={"tags": [INTERNAL_CONTRIBUTOR_TAG]},
        )
        if not isinstance(extracted, Contribution):
            raise TypeError(f"Unexpected contribution result: {extracted!r}")

        evidence_text = "".join(
            str(getattr(message, "content", message)) for message in (evidence_messages or [])
        )
        kept_findings = []
        for finding in extracted.findings:
            source_url = getattr(finding.source, "url", None)
            if source_url is None or source_url in evidence_text:
                kept_findings.append(finding)
        dropped = len(extracted.findings) - len(kept_findings)
        if dropped:
            _logger.debug(
                "Dropped %d finding(s) from %s with URLs absent from tool evidence",
                dropped,
                agent_name,
            )
        return extracted.model_copy(
            update={"agent": agent_name, "findings": kept_findings, "analysis": content}
        )
    except Exception:
        return Contribution(
            agent=agent_name,
            summary=content or "No contribution.",
            analysis=content or None,
            findings=[],
        )
