import logging
import threading
from bisect import bisect_right
from dataclasses import dataclass

from ..config import get_settings
from .merge import MergedSegment

log = logging.getLogger(__name__)

_pipeline = None
_pipeline_lock = threading.Lock()


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class DiarizationUnavailable(RuntimeError):
    pass


def _load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        s = get_settings()
        token = s.HF_TOKEN or None
        try:
            from pyannote.audio import Pipeline  # type: ignore
        except ImportError as exc:
            raise DiarizationUnavailable(
                "pyannote.audio is not installed in the worker image"
            ) from exc

        log.info("Loading diarization pipeline=%s device=%s", s.DIARIZATION_MODEL, s.DIARIZATION_DEVICE)
        try:
            pipeline = Pipeline.from_pretrained(s.DIARIZATION_MODEL, use_auth_token=token)
        except Exception as exc:
            raise DiarizationUnavailable(
                f"could not load diarization model '{s.DIARIZATION_MODEL}'. "
                "Make sure HF_TOKEN is set and you have accepted the model terms on HuggingFace. "
                f"Underlying error: {exc}"
            ) from exc

        if s.DIARIZATION_DEVICE and s.DIARIZATION_DEVICE.lower() != "cpu":
            try:
                import torch  # type: ignore

                pipeline.to(torch.device(s.DIARIZATION_DEVICE))
            except Exception as exc:
                log.warning("could not move diarization pipeline to %s: %s", s.DIARIZATION_DEVICE, exc)

        _pipeline = pipeline
    return _pipeline


def diarize_audio(
    wav_path: str,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list[SpeakerTurn]:
    pipeline = _load_pipeline()
    kwargs: dict = {}
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers

    annotation = pipeline(wav_path, **kwargs)
    turns: list[SpeakerTurn] = []
    for segment, _, label in annotation.itertracks(yield_label=True):
        if segment.end <= segment.start:
            continue
        turns.append(SpeakerTurn(start=float(segment.start), end=float(segment.end), speaker=str(label)))
    turns.sort(key=lambda t: t.start)
    log.info("diarized %s -> %d turns, %d speakers",
             wav_path, len(turns), len({t.speaker for t in turns}))
    return turns


def assign_speakers(segments: list[MergedSegment], turns: list[SpeakerTurn]) -> list[str | None]:
    """Pick the speaker whose turn overlaps each segment the most.

    Returned list is parallel to `segments`. Entries are None when no diarization
    turn overlaps a given segment (e.g. silence misalignment at the very edges).
    """
    if not turns:
        return [None] * len(segments)

    starts = [t.start for t in turns]
    out: list[str | None] = []
    for seg in segments:
        idx = max(0, bisect_right(starts, seg.end) - 1)
        best_overlap = 0.0
        best_speaker: str | None = None
        # scan a small window around the binary-search hit since turns can be short
        for j in range(max(0, idx - 1), min(len(turns), idx + 2)):
            t = turns[j]
            overlap = max(0.0, min(seg.end, t.end) - max(seg.start, t.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = t.speaker
        out.append(best_speaker)
    return out
