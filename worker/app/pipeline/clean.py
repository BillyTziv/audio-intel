import logging
import re

from .merge import MergedSegment

log = logging.getLogger(__name__)

_FILLERS = {
    "ε", "εε", "εμ", "εεμ", "ααα", "αα", "ε...", "εμμ",
    "uh", "um", "uhh", "umm", "er", "erm",
}
_WS = re.compile(r"\s+")
_PUNCT_DUPES = re.compile(r"([,.!?;:·…])\1+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:·…])")


def segments_to_raw_text(segments: list[MergedSegment]) -> str:
    return "\n".join(s.text.strip() for s in segments if s.text.strip())


def clean_text(text: str) -> str:
    if not text:
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        words = [w for w in line.split() if w.lower() not in _FILLERS]
        line = " ".join(words)
        line = _PUNCT_DUPES.sub(r"\1", line)
        line = _SPACE_BEFORE_PUNCT.sub(r"\1", line)
        line = _WS.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)
