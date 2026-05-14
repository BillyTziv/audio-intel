import logging
import threading
from dataclasses import dataclass

from faster_whisper import WhisperModel

from ..config import get_settings

log = logging.getLogger(__name__)

_model: WhisperModel | None = None
_model_lock = threading.Lock()


def _get_model() -> WhisperModel:
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            s = get_settings()
            log.info(
                "Loading faster-whisper model=%s device=%s compute=%s",
                s.WHISPER_MODEL, s.WHISPER_DEVICE, s.WHISPER_COMPUTE_TYPE,
            )
            _model = WhisperModel(
                s.WHISPER_MODEL,
                device=s.WHISPER_DEVICE,
                compute_type=s.WHISPER_COMPUTE_TYPE,
                download_root=s.WHISPER_MODEL_DIR,
            )
    return _model


@dataclass
class Segment:
    start: float
    end: float
    text: str


def transcribe_chunk(path: str, language: str | None = None) -> tuple[list[Segment], dict]:
    model = _get_model()
    segments_iter, info = model.transcribe(
        path,
        language=language or None,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )
    out: list[Segment] = []
    for s in segments_iter:
        text = (s.text or "").strip()
        if not text:
            continue
        out.append(Segment(start=float(s.start), end=float(s.end), text=text))

    meta = {
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
    }
    log.info("transcribed %s -> %d segments (lang=%s)", path, len(out), meta["language"])
    return out, meta
