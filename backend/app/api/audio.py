import json
import logging
import uuid
from pathlib import Path
from typing import Literal
from uuid import UUID

from datetime import datetime

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import get_current_user, get_db
from ..models.audio_job import AudioJob, JobStatus
from ..models.transcript import Transcript
from ..models.user import User
from ..schemas.audio import AudioJobListOut, AudioJobOut, AudioJobUpdate, UploadResponse
from ..schemas.transcript import TranscriptOut
from ..services.queue import enqueue_job
from ..services.storage import save_upload

router = APIRouter(prefix="/audio", tags=["audio"])
log = logging.getLogger(__name__)


def _validate_filename(filename: str | None) -> str:
    settings = get_settings()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_AUDIO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file extension '{ext}'. allowed: {', '.join(settings.ALLOWED_AUDIO_EXT)}",
        )
    return ext


def _get_job_for_user(db: Session, job_id: UUID, user: User) -> AudioJob:
    job = db.query(AudioJob).filter(AudioJob.id == job_id, AudioJob.user_id == user.id).one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _clean_str(v: str | None, max_len: int) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    return v[:max_len]


def _parse_participants(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    cleaned = [p[:120] for p in parts if p]
    return cleaned or None


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(...),
    diarize: bool = Form(False),
    title: str | None = Form(None),
    project: str | None = Form(None),
    description: str | None = Form(None),
    meeting_date: datetime | None = Form(None),
    participants: str | None = Form(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> UploadResponse:
    _validate_filename(file.filename)
    job_id = uuid.uuid4()

    try:
        stored_name, file_path, size = await save_upload(file, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        log.exception("Upload failed for user=%s", current.username)
        raise HTTPException(status_code=500, detail=f"upload failed: {exc}")

    job = AudioJob(
        id=job_id,
        user_id=current.id,
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_path=file_path,
        mime_type=file.content_type,
        size_bytes=size,
        status=JobStatus.queued,
        diarize=diarize,
        title=_clean_str(title, 512),
        project=_clean_str(project, 255),
        description=_clean_str(description, 10000),
        meeting_date=meeting_date,
        participants=_parse_participants(participants),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        enqueue_job(job.id)
    except Exception as exc:
        log.exception("Failed to enqueue job %s", job.id)
        job.status = JobStatus.failed
        job.error_message = f"enqueue failed: {exc}"
        db.commit()
        raise HTTPException(status_code=500, detail="failed to enqueue processing")

    return UploadResponse(job_id=job.id, status=job.status)


@router.get("/jobs", response_model=AudioJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AudioJobListOut:
    q = db.query(AudioJob).filter(AudioJob.user_id == current.id).order_by(AudioJob.created_at.desc())
    total = q.count()
    items = q.limit(limit).offset(offset).all()
    return AudioJobListOut(items=[AudioJobOut.model_validate(i) for i in items], total=total)


@router.get("/jobs/{job_id}", response_model=AudioJobOut)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> AudioJobOut:
    job = _get_job_for_user(db, job_id, current)
    return AudioJobOut.model_validate(job)


@router.patch("/jobs/{job_id}", response_model=AudioJobOut)
def update_job(
    job_id: UUID,
    payload: AudioJobUpdate = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> AudioJobOut:
    job = _get_job_for_user(db, job_id, current)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        job.title = _clean_str(data["title"], 512)
    if "project" in data:
        job.project = _clean_str(data["project"], 255)
    if "description" in data:
        job.description = _clean_str(data["description"], 10000)
    if "meeting_date" in data:
        job.meeting_date = data["meeting_date"]
    if "participants" in data:
        parts = data["participants"]
        if parts is None:
            job.participants = None
        else:
            cleaned = [p.strip()[:120] for p in parts if p and p.strip()]
            job.participants = cleaned or None
    db.commit()
    db.refresh(job)
    return AudioJobOut.model_validate(job)


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptOut)
def get_transcript(
    job_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TranscriptOut:
    job = _get_job_for_user(db, job_id, current)
    transcript = db.query(Transcript).filter(Transcript.job_id == job.id).one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="transcript not ready")
    return TranscriptOut.model_validate(transcript)


def _segments_to_srt(segments: list[dict]) -> str:
    def fmt(seconds: float) -> str:
        if seconds < 0:
            seconds = 0
        ms = int(round((seconds - int(seconds)) * 1000))
        s = int(seconds) % 60
        m = (int(seconds) // 60) % 60
        h = int(seconds) // 3600
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        text = (seg.get("text") or "").strip()
        speaker = seg.get("speaker")
        if speaker:
            text = f"[{speaker}] {text}"
        lines.append(str(i))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


@router.get("/jobs/{job_id}/download/{fmt}")
def download(
    job_id: UUID,
    fmt: Literal["txt", "json", "srt", "summary", "clean"],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    job = _get_job_for_user(db, job_id, current)
    transcript = db.query(Transcript).filter(Transcript.job_id == job.id).one_or_none()
    if not transcript:
        raise HTTPException(status_code=404, detail="transcript not ready")

    base_name = Path(job.original_filename).stem or str(job.id)

    if fmt == "txt":
        body = transcript.raw_text or ""
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": f'attachment; filename="{base_name}.txt"'},
        )
    if fmt == "clean":
        body = transcript.cleaned_text or transcript.raw_text or ""
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": f'attachment; filename="{base_name}.clean.txt"'},
        )
    if fmt == "summary":
        parts: list[str] = []
        if transcript.summary:
            parts.append("# Summary\n\n" + transcript.summary)
        if transcript.key_points:
            parts.append("# Key Points\n\n" + "\n".join(f"- {x}" for x in transcript.key_points))
        if transcript.decisions:
            parts.append("# Decisions\n\n" + "\n".join(f"- {x}" for x in transcript.decisions))
        if transcript.action_items:
            parts.append(
                "# Action Items\n\n"
                + "\n".join(f"- {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}" for x in transcript.action_items)
            )
        body = "\n\n".join(parts) if parts else "(no summary available)"
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": f'attachment; filename="{base_name}.summary.md"'},
        )
    if fmt == "json":
        body = {
            "job_id": str(job.id),
            "language": transcript.language,
            "raw_text": transcript.raw_text,
            "cleaned_text": transcript.cleaned_text,
            "summary": transcript.summary,
            "key_points": transcript.key_points,
            "decisions": transcript.decisions,
            "action_items": transcript.action_items,
            "segments": transcript.segments,
            "speakers": transcript.speakers,
        }
        return Response(
            content=json.dumps(body, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.json"'},
        )
    if fmt == "srt":
        body = _segments_to_srt(transcript.segments or [])
        return PlainTextResponse(
            body,
            media_type="application/x-subrip",
            headers={"Content-Disposition": f'attachment; filename="{base_name}.srt"'},
        )
    raise HTTPException(status_code=400, detail="unsupported format")
