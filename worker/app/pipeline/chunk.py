import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class ChunkingError(Exception):
    pass


@dataclass
class Chunk:
    index: int
    start: float
    end: float
    path: str


def split_wav(src_wav: str, dest_dir: str, duration: float, chunk_seconds: int, overlap_seconds: int) -> list[Chunk]:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    if duration <= chunk_seconds + overlap_seconds:
        return [Chunk(index=0, start=0.0, end=duration, path=src_wav)]

    chunks: list[Chunk] = []
    index = 0
    start = 0.0
    while start < duration:
        end = min(start + chunk_seconds + overlap_seconds, duration)
        out = os.path.join(dest_dir, f"chunk_{index:03d}.wav")
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{start:.3f}",
                "-to", f"{end:.3f}",
                "-i", src_wav,
                "-c:a", "pcm_s16le",
                "-ac", "1", "-ar", "16000",
                out,
            ],
            check=False, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise ChunkingError(f"ffmpeg split failed at chunk {index}: {proc.stderr.strip()[:400]}")
        if not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise ChunkingError(f"empty chunk produced at index {index}")

        chunks.append(Chunk(index=index, start=start, end=end, path=out))
        index += 1
        start += chunk_seconds

    log.info("split into %d chunks (%.1fs each, %ds overlap)", len(chunks), chunk_seconds, overlap_seconds)
    return chunks
