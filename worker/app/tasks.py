import logging
import os
import sys
import time
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
from .pipeline.diarize import DiarizationUnavailable, SpeakerTurn, assign_speakers, diarize_audio
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
        timings: dict[str, float] = {}

        _set_status(db, job, JobStatus.validating, 0.02)
        _t = time.perf_counter()
        duration = validate_file(job.file_path)
        timings["validate"] = time.perf_counter() - _t
        job.duration_seconds = duration
        db.commit()

        _set_status(db, job, JobStatus.converting, 0.05)
        _t = time.perf_counter()
        wav_path = to_wav_mono_16k(job.file_path, str(work_dir))
        timings["convert"] = time.perf_counter() - _t

        _set_status(db, job, JobStatus.chunking, 0.10)
        _t = time.perf_counter()
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
        timings["chunk"] = time.perf_counter() - _t

        diarize_requested = bool(getattr(job, "diarize", False))
        diarize_active = diarize_requested and settings.DIARIZATION_ENABLED
        if diarize_requested and not settings.DIARIZATION_ENABLED:
            log.warning(
                "job=%s requested diarization but DIARIZATION_ENABLED is off; skipping",
                job.id,
            )

        # Reserve the tail of the progress bar for diarization when enabled.
        transcribe_end = 0.70 if diarize_active else 0.80

        _set_status(db, job, JobStatus.transcribing, 0.15)
        _t = time.perf_counter()
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
            progress = 0.15 + (transcribe_end - 0.15) * ((i + 1) / total)
            _set_status(db, job, JobStatus.transcribing, progress)

        timings["transcribe"] = time.perf_counter() - _t

        turns: list[SpeakerTurn] = []
        diarize_error: str | None = None
        if diarize_active:
            _set_status(db, job, JobStatus.diarizing, transcribe_end)
            _t = time.perf_counter()
            try:
                turns = diarize_audio(wav_path)
            except DiarizationUnavailable as exc:
                diarize_error = str(exc)
                log.warning("job=%s diarization unavailable: %s", job.id, exc)
            except Exception as exc:
                diarize_error = f"diarization failed: {exc}"
                log.exception("job=%s diarization failed", job.id)
            timings["diarize"] = time.perf_counter() - _t

        _set_status(db, job, JobStatus.summarizing, 0.82)
        _t = time.perf_counter()
        merged = merge_chunk_transcripts(
            per_chunk=per_chunk,
            chunk_seconds=settings.CHUNK_SECONDS,
            overlap_seconds=settings.OVERLAP_SECONDS,
        )
        speakers_per_segment: list[str | None] = (
            assign_speakers(merged, turns) if turns else [None] * len(merged)
        )
        raw_text = segments_to_raw_text(merged)
        cleaned = clean_text(raw_text)
        timings["merge_clean"] = time.perf_counter() - _t

        _t = time.perf_counter()
        summary_result = summarize(cleaned or raw_text, language=detected_language)
        timings["summarize"] = time.perf_counter() - _t

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
            {
                "start": round(s.start, 3),
                "end": round(s.end, 3),
                "text": s.text,
                "speaker": speakers_per_segment[i],
            }
            for i, s in enumerate(merged)
        ]
        unique_speakers = sorted({sp for sp in speakers_per_segment if sp})
        transcript.speakers = unique_speakers or None
        db.commit()

        if diarize_error:
            existing = job.error_message or ""
            job.error_message = (existing + ("\n" if existing else "") + diarize_error)[:4000]
            db.commit()

        job.completed_at = _utcnow()
        _set_status(db, job, JobStatus.completed, 1.0)
        log.info("job=%s completed (%d segments, %d chars)", job.id, len(merged), len(raw_text))

        total_time = sum(timings.values())
        rtf = (total_time / duration) if duration and duration > 0 else 0.0
        breakdown = " ".join(
            f"{k}={v:.2f}s({(100 * v / total_time):.0f}%)" for k, v in timings.items()
        ) if total_time > 0 else ""
        log.info(
            "timings job=%s audio=%.1fs total=%.1fs rtf=%.2fx | %s",
            job.id, duration or 0.0, total_time, rtf, breakdown,
        )

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
