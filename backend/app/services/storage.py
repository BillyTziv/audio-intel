import logging
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from ..config import get_settings

log = logging.getLogger(__name__)


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if not ext or len(ext) > 8:
        return ".bin"
    return ext


async def save_upload(file: UploadFile, job_id: uuid.UUID) -> tuple[str, str, int]:
    settings = get_settings()
    base = Path(settings.UPLOAD_DIR) / str(job_id)
    base.mkdir(parents=True, exist_ok=True)

    ext = _safe_ext(file.filename or "audio")
    stored_name = f"original{ext}"
    target = base / stored_name

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    chunk_size = 1024 * 1024

    async with aiofiles.open(target, "wb") as out:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                await out.close()
                try:
                    os.remove(target)
                except OSError:
                    pass
                raise ValueError(f"file exceeds maximum size of {settings.MAX_UPLOAD_MB}MB")
            await out.write(chunk)

    log.info("Saved upload job=%s path=%s bytes=%d", job_id, target, written)
    return stored_name, str(target), written


def output_path(job_id: uuid.UUID, filename: str) -> Path:
    settings = get_settings()
    base = Path(settings.OUTPUT_DIR) / str(job_id)
    base.mkdir(parents=True, exist_ok=True)
    return base / filename
