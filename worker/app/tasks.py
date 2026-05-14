import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .models import AudioChunk, AudioJob, ChunkStatus, JobStatus, Transcript
from .pipeline.chunk import split_wav
from .pipeline.clean import clean_text, segments_to_raw_text
from .pipeline.convert import to_wav_mono_16k
from .pipeline.merge import merge_chunk_transcripts
from .pipeline.summarize import summarize
from .pipeline.transcribe import transcribe_chunk
from .pipeline.validate import validate_file


def _configure_logging() -> None:
    level = getattr(logging, get_settings().LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


_configure_logging()
log = logging.getLogger("worker.tasks")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set_status(db: Session, job: AudioJob, status: JobStatus, progress: float | None = None) -> None:
    job.status = status
    if progress is not None:
        job.progress = max(0.0, min(1.0, progress))
    job.updated_at = _utcnow()
    db.commit()
    log.info("job=%s -> %s (progress=%.2f)", job.id, status.value, job.progress)


def process_audio_job(job_id_str: str) -> None:
    job_id = UUID(job_id_str)
    settings = get_settings()
    db: Session = SessionLocal()
    job = db.query(AudioJob).filter(AudioJob.id == job_id).one_or_none()
    if not job:
        log.error("job %s not found", job_id)
        db.close()
        return

    work_dir = Path(settings.UPLOAD_DIR) / str(job_id) / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        job.started_at = _utcnow()
        _set_status(db, job, JobStatus.validating, 0.02)
        duration = validate_file(job.file_path)
        job.duration_seconds = duration
        db.commit()

        _set_status(db, job, JobStatus.converting, 0.05)
        wav_path = to_wav_mono_16k(job.file_path, str(work_dir))

        _set_status(db, job, JobStatus.chunking, 0.10)
        chunk_dir = work_dir / "chunks"
        chunks = split_wav(
            src_wav=wav_path,
            dest_dir=str(chunk_dir),
            duration=duration,
            chunk_seconds=settings.CHUNK_SECONDS,
            overlap_seconds=settings.OVERLAP_SECONDS,
        )

        db.query(AudioChunk).filter(AudioChunk.job_id == job.id).delete()
        for c in chunks:
            db.add(AudioChunk(
                job_id=job.id, index=c.index, start_seconds=c.start, end_seconds=c.end,
                file_path=c.path, status=ChunkStatus.pending,
            ))
        db.commit()

        _set_status(db, job, JobStatus.transcribing, 0.15)
        per_chunk: list = []
        detected_language: str | None = None
        total = max(1, len(chunks))

        for i, c in enumerate(chunks):
            chunk_row = db.query(AudioChunk).filter(
                AudioChunk.job_id == job.id, AudioChunk.index == c.index
            ).one()
            chunk_row.status = ChunkStatus.processing
            db.commit()

            try:
                segments, meta = transcribe_chunk(c.path, language=settings.WHISPER_LANGUAGE)
                if detected_language is None:
                    detected_language = meta.get("language") or settings.WHISPER_LANGUAGE
                per_chunk.append((c, segments))
                chunk_row.status = ChunkStatus.done
            except Exception as exc:
                chunk_row.status = ChunkStatus.failed
                chunk_row.error_message = str(exc)[:500]
                db.commit()
                raise

            db.commit()
            progress = 0.15 + 0.65 * ((i + 1) / total)
            _set_status(db, job, JobStatus.transcribing, progress)

        _set_status(db, job, JobStatus.summarizing, 0.82)
        merged = merge_chunk_transcripts(
            per_chunk=per_chunk,
            chunk_seconds=settings.CHUNK_SECONDS,
            overlap_seconds=settings.OVERLAP_SECONDS,
        )
        raw_text = segments_to_raw_text(merged)
        cleaned = clean_text(raw_text)

        summary_result = summarize(cleaned or raw_text, language=detected_language)

        transcript = db.query(Transcript).filter(Transcript.job_id == job.id).one_or_none()
        if not transcript:
            transcript = Transcript(job_id=job.id)
            db.add(transcript)
        transcript.language = detected_language
        transcript.raw_text = raw_text
        transcript.cleaned_text = cleaned
        transcript.summary = summary_result.summary
        transcript.key_points = summary_result.key_points
        transcript.decisions = summary_result.decisions
        transcript.action_items = summary_result.action_items
        transcript.segments = [
            {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text}
            for s in merged
        ]
        db.commit()

        job.completed_at = _utcnow()
        _set_status(db, job, JobStatus.completed, 1.0)
        log.info("job=%s completed (%d segments, %d chars)", job.id, len(merged), len(raw_text))

    except Exception as exc:
        log.exception("job %s failed", job_id)
        try:
            job.error_message = (str(exc) + "\n" + traceback.format_exc())[:4000]
            job.status = JobStatus.failed
            job.completed_at = _utcnow()
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        try:
            for f in (work_dir / "chunks").glob("chunk_*.wav") if (work_dir / "chunks").exists() else []:
                try:
                    os.remove(f)
                except OSError:
                    pass
        except Exception:
            pass
        db.close()
