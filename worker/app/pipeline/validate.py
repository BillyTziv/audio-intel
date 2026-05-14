import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise ValidationError("ffmpeg/ffprobe not available on PATH")


def probe(path: str) -> dict:
    ensure_ffmpeg()
    if not os.path.isfile(path):
        raise ValidationError(f"file not found: {path}")
    if os.path.getsize(path) == 0:
        raise ValidationError("file is empty")

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValidationError(f"ffprobe failed: {proc.stderr.strip()[:400]}")
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"could not parse ffprobe output: {exc}")

    streams = info.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise ValidationError("no audio stream found in file")

    fmt = info.get("format") or {}
    duration = fmt.get("duration")
    if duration is None:
        raise ValidationError("could not determine media duration")
    try:
        duration_f = float(duration)
    except (TypeError, ValueError):
        raise ValidationError(f"invalid duration value: {duration!r}")
    if duration_f <= 0:
        raise ValidationError("media duration is zero")

    return {"duration": duration_f, "format": fmt, "streams": streams}


def validate_file(path: str) -> float:
    info = probe(path)
    log.info("validated path=%s duration=%.2fs", Path(path).name, info["duration"])
    return float(info["duration"])
