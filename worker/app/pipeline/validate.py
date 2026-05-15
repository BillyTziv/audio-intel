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
    duration_f = _coerce_duration(fmt.get("duration"))
    if duration_f is None:
        for s in streams:
            if s.get("codec_type") == "audio":
                duration_f = _coerce_duration(s.get("duration"))
                if duration_f is not None:
                    break
    if duration_f is None:
        duration_f = _duration_via_packet_count(path)
    if duration_f is None:
        raise ValidationError("could not determine media duration")
    if duration_f <= 0:
        raise ValidationError("media duration is zero")

    return {"duration": duration_f, "format": fmt, "streams": streams}


def _coerce_duration(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _duration_via_packet_count(path: str) -> float | None:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-count_packets",
            "-show_entries", "packet=pts_time,duration_time",
            "-of", "csv=p=0",
            path,
        ],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    last_end = 0.0
    for line in proc.stdout.strip().splitlines():
        parts = line.split(",")
        pts = _coerce_duration(parts[0]) if parts and parts[0] else None
        dur = _coerce_duration(parts[1]) if len(parts) > 1 and parts[1] else None
        end = (pts or 0.0) + (dur or 0.0)
        if end > last_end:
            last_end = end
    return last_end if last_end > 0 else None


def validate_file(path: str) -> float:
    info = probe(path)
    log.info("validated path=%s duration=%.2fs", Path(path).name, info["duration"])
    return float(info["duration"])
