import logging
from dataclasses import dataclass

from .llm import LLMError, extract_json_block, get_provider

log = logging.getLogger(__name__)


SYSTEM_PROMPT_EL = (
    "Είσαι βοηθός που αναλύει απομαγνητοφωνημένα ηχητικά (συναντήσεις, "
    "συνεντεύξεις, σημειώσεις) στα Ελληνικά. Παράγεις πάντα έγκυρο JSON, "
    "χωρίς επεξηγήσεις εκτός JSON."
)

USER_TEMPLATE_EL = """Αναλύεις το παρακάτω κείμενο.

Επέστρεψε ΜΟΝΟ JSON με αυτά τα κλειδιά (όλα στα Ελληνικά):
{{
  "summary": "σύντομη περίληψη 4-8 προτάσεων",
  "key_points": ["μέχρι 10 σύντομα bullet points"],
  "decisions": ["αποφάσεις που πάρθηκαν, ή κενή λίστα"],
  "action_items": [
    {{"task": "...", "owner": "ή null", "due": "ή null"}}
  ]
}}

Κείμενο:
\"\"\"
{text}
\"\"\"
"""


SYSTEM_PROMPT_EN = (
    "You analyze meeting/interview/audio transcripts. Always respond with "
    "valid JSON only — no commentary, no markdown fences."
)

USER_TEMPLATE_EN = """Analyze the transcript below.

Return ONLY a JSON object with these keys:
{{
  "summary": "concise 4-8 sentence summary",
  "key_points": ["up to 10 short bullets"],
  "decisions": ["decisions made, or empty list"],
  "action_items": [
    {{"task": "...", "owner": "or null", "due": "or null"}}
  ]
}}

Transcript:
\"\"\"
{text}
\"\"\"
"""


@dataclass
class SummaryResult:
    summary: str | None
    key_points: list
    decisions: list
    action_items: list


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head
    return text[:head] + "\n\n[...]\n\n" + text[-tail:]


def summarize(text: str, language: str | None = "el") -> SummaryResult:
    empty = SummaryResult(summary=None, key_points=[], decisions=[], action_items=[])
    if not text or not text.strip():
        return empty

    provider = get_provider()
    if provider is None:
        log.info("LLM_PROVIDER=none, skipping summarization")
        return empty

    use_greek = (language or "").lower().startswith("el")
    system = SYSTEM_PROMPT_EL if use_greek else SYSTEM_PROMPT_EN
    template = USER_TEMPLATE_EL if use_greek else USER_TEMPLATE_EN

    truncated = _truncate(text, 24000)
    user = template.format(text=truncated)

    try:
        raw = provider.complete(system=system, user=user, max_tokens=2048)
    except LLMError as exc:
        log.warning("Summarization failed: %s", exc)
        return empty

    data = extract_json_block(raw) or {}
    return SummaryResult(
        summary=(data.get("summary") or "").strip() or None,
        key_points=list(data.get("key_points") or []),
        decisions=list(data.get("decisions") or []),
        action_items=list(data.get("action_items") or []),
    )
