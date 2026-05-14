import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class ConversionError(Exception):
    pass


def to_wav_mono_16k(src: str, dest_dir: str) -> str:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    out = os.path.join(dest_dir, "audio.wav")

    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", src,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-sample_fmt", "s16",
            "-c:a", "pcm_s16le",
            out,
        ],
        check=False, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ConversionError(f"ffmpeg conversion failed: {proc.stderr.strip()[:400]}")
    if not os.path.isfile(out) or os.path.getsize(out) == 0:
        raise ConversionError("conversion produced no output")

    log.info("converted %s -> %s (%d bytes)", Path(src).name, out, os.path.getsize(out))
    return out
