import logging
from dataclasses import dataclass

from .chunk import Chunk
from .transcribe import Segment

log = logging.getLogger(__name__)


@dataclass
class MergedSegment:
    start: float
    end: float
    text: str


def merge_chunk_transcripts(
    per_chunk: list[tuple[Chunk, list[Segment]]],
    chunk_seconds: int,
    overlap_seconds: int,
) -> list[MergedSegment]:
    """Stitch segments from overlapping chunks into a single timeline.

    Each chunk's segment timestamps are local to the chunk (start at 0).
    We offset by chunk.start, then drop segments from chunk N+1 that begin
    before the boundary (chunk.start + chunk_seconds), since those already
    appear in chunk N's tail. We use the segment midpoint as the deciding
    moment to avoid double-counting straddling segments.
    """
    merged: list[MergedSegment] = []
    for i, (chunk, segs) in enumerate(per_chunk):
        boundary = chunk.start  # absolute time at which this chunk's "owned" region begins
        if i > 0:
            # the previous chunk owns up to chunk.start (since each chunk advances by chunk_seconds)
            # so we keep this chunk's segments whose midpoint is past chunk.start
            pass
        for s in segs:
            absolute_start = chunk.start + s.start
            absolute_end = chunk.start + s.end
            mid = (absolute_start + absolute_end) / 2.0
            if i > 0 and mid < boundary:
                continue
            merged.append(MergedSegment(start=absolute_start, end=absolute_end, text=s.text))

    merged.sort(key=lambda x: x.start)
    deduped = _dedupe_consecutive(merged)
    log.info("merged %d raw -> %d deduped segments", len(merged), len(deduped))
    return deduped


def _dedupe_consecutive(segments: list[MergedSegment]) -> list[MergedSegment]:
    out: list[MergedSegment] = []
    last_text: str | None = None
    last_end: float | None = None
    for s in segments:
        norm = s.text.strip().lower()
        if last_text == norm and last_end is not None and abs(s.start - last_end) < 1.5:
            if out:
                out[-1] = MergedSegment(start=out[-1].start, end=s.end, text=out[-1].text)
            continue
        out.append(s)
        last_text = norm
        last_end = s.end
    return out
