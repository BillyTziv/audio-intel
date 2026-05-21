import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.security import decode_token
from ..deps import get_current_user, get_db
from ..models.audio_job import AudioJob, JobStatus
from ..models.user import User
from ..schemas.teams import (
    TeamsAuthStartResponse,
    TeamsConnectionStatus,
    TeamsImportRequest,
    TeamsImportResponse,
    TeamsMeetingListOut,
    TeamsMeetingSummary,
)
from ..services import msgraph
from ..services.queue import enqueue_job

router = APIRouter(prefix="/teams", tags=["teams"])
log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_state(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": user.username,
        "uid": str(user.id),
        "purpose": "ms_oauth_state",
        "exp": int((_utcnow() + timedelta(minutes=15)).timestamp()),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def _user_from_state(db: Session, state: str) -> User:
    try:
        payload = decode_token(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid state")
    if payload.get("purpose") != "ms_oauth_state":
        raise HTTPException(status_code=400, detail="invalid state purpose")
    uid = payload.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="invalid state subject")
    user = db.query(User).filter(User.id == uid, User.is_active.is_(True)).one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="user not found for state")
    return user


@router.get("/auth/start", response_model=TeamsAuthStartResponse)
def auth_start(current: User = Depends(get_current_user)) -> TeamsAuthStartResponse:
    s = get_settings()
    if not s.MS_CLIENT_ID or not s.MS_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Microsoft Graph integration not configured")
    state = _make_state(current)
    url = msgraph.build_authorize_url(state)
    return TeamsAuthStartResponse(authorize_url=url, state=state)


@router.get("/auth/callback")
def auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    s = get_settings()
    if error:
        log.warning("MS OAuth error: %s — %s", error, error_description)
        return RedirectResponse(
            f"{s.MS_POST_LOGIN_REDIRECT}?ms_status=error&reason={error}", status_code=302
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")
    user = _user_from_state(db, state)

    try:
        bundle = msgraph.exchange_code(code)
        me = msgraph.get_me(bundle.access_token)
        msgraph.upsert_account(db, user, bundle, me)
    except msgraph.MsGraphError as e:
        log.exception("MS OAuth callback failed for user=%s", user.username)
        return RedirectResponse(
            f"{s.MS_POST_LOGIN_REDIRECT}?ms_status=error&reason={str(e)[:120]}", status_code=302
        )

    return RedirectResponse(f"{s.MS_POST_LOGIN_REDIRECT}?ms_status=connected", status_code=302)


@router.get("/auth/status", response_model=TeamsConnectionStatus)
def auth_status(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TeamsConnectionStatus:
    acct = msgraph.get_account_for_user(db, current)
    if not acct:
        return TeamsConnectionStatus(connected=False)
    return TeamsConnectionStatus(
        connected=True,
        ms_display_name=acct.ms_display_name,
        ms_user_principal_name=acct.ms_user_principal_name,
        token_expires_at=acct.token_expires_at,
    )


@router.delete("/auth")
def auth_disconnect(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> dict[str, bool]:
    acct = msgraph.get_account_for_user(db, current)
    if acct:
        db.delete(acct)
        db.commit()
    return {"disconnected": True}


@router.get("/meetings", response_model=TeamsMeetingListOut)
def list_meetings(
    days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TeamsMeetingListOut:
    try:
        acct = msgraph.require_account(db, current)
    except msgraph.MsNotConnectedError:
        raise HTTPException(status_code=409, detail="Microsoft account not connected")

    try:
        events = msgraph.list_recent_meetings(db, acct, days=days)
    except msgraph.MsGraphError as e:
        raise HTTPException(status_code=502, detail=f"Microsoft Graph error: {e}")

    items: list[TeamsMeetingSummary] = []
    for ev in events:
        om = ev.get("onlineMeeting") or {}
        attendees = []
        for a in ev.get("attendees", []) or []:
            em = (a.get("emailAddress") or {})
            name = em.get("name") or em.get("address")
            if name:
                attendees.append(name)
        items.append(
            TeamsMeetingSummary(
                event_id=ev.get("id", ""),
                subject=ev.get("subject"),
                start=_parse_dt(ev.get("start")),
                end=_parse_dt(ev.get("end")),
                organizer=((ev.get("organizer") or {}).get("emailAddress") or {}).get("name"),
                join_url=om.get("joinUrl") or "",
                web_link=ev.get("webLink"),
                attendees=attendees,
            )
        )
    return TeamsMeetingListOut(items=items)


def _parse_dt(obj: Any) -> datetime | None:
    if not obj:
        return None
    if isinstance(obj, str):
        raw = obj
    else:
        raw = obj.get("dateTime")
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str, fallback: str) -> str:
    base = _SAFE_NAME.sub("_", name).strip("._")
    return base or fallback


@router.post("/meetings/import", response_model=TeamsImportResponse)
def import_meeting(
    payload: TeamsImportRequest = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> TeamsImportResponse:
    settings = get_settings()
    notes: list[str] = []

    try:
        acct = msgraph.require_account(db, current)
    except msgraph.MsNotConnectedError:
        raise HTTPException(status_code=409, detail="Microsoft account not connected")

    join_url = payload.join_url.strip()
    if not join_url:
        raise HTTPException(status_code=400, detail="join_url is required")
    parsed = urlparse(join_url)
    if parsed.scheme not in ("http", "https") or "teams.microsoft.com" not in (parsed.netloc or ""):
        raise HTTPException(status_code=400, detail="join_url must be a Teams meeting URL")

    try:
        meeting = msgraph.get_online_meeting_by_join_url(db, acct, join_url)
    except msgraph.MsGraphError as e:
        raise HTTPException(status_code=502, detail=f"Microsoft Graph error: {e}")

    meeting_id = meeting.get("id")
    if not meeting_id:
        raise HTTPException(status_code=502, detail="Meeting lookup returned no id")

    existing = (
        db.query(AudioJob)
        .filter(AudioJob.user_id == current.id, AudioJob.source_meeting_id == meeting_id)
        .one_or_none()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This meeting was already imported (job {existing.id})",
        )

    subject = meeting.get("subject") or payload.title or "Teams meeting"
    meeting_date = _parse_dt(meeting.get("startDateTime")) or _parse_dt(meeting.get("creationDateTime"))

    job_id = uuid.uuid4()
    job_dir = Path(settings.UPLOAD_DIR) / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    recording_downloaded = False
    stored_name = ""
    file_path = ""
    size_bytes = 0

    try:
        recordings = msgraph.list_recordings(db, acct, meeting_id)
    except msgraph.MsGraphError as e:
        notes.append(f"recordings lookup failed: {e}")
        recordings = []

    if recordings:
        rec = recordings[0]
        rec_id = rec.get("id")
        ext = ".mp4"
        stored_name = _safe_filename(f"{subject}{ext}", f"recording{ext}")
        target = job_dir / stored_name
        try:
            size_bytes = msgraph.download_recording(db, acct, meeting_id, rec_id, target)
            file_path = str(target)
            recording_downloaded = True
        except Exception as e:
            log.exception("Recording download failed for meeting=%s", meeting_id)
            notes.append(f"recording download failed: {e}")

    if not recording_downloaded:
        raise HTTPException(
            status_code=422,
            detail=(
                "No downloadable recording is available for this meeting. "
                "The meeting may not have been recorded, or you may not be the organizer. "
                "Recording/transcript artifacts are only accessible to the meeting organizer "
                "via delegated permissions."
            ),
        )

    transcript_vtt: str | None = None
    transcript_imported = False
    try:
        transcripts = msgraph.list_transcripts(db, acct, meeting_id)
        if transcripts:
            tid = transcripts[0].get("id")
            transcript_vtt = msgraph.fetch_transcript_vtt(db, acct, meeting_id, tid)
            transcript_imported = bool(transcript_vtt)
        else:
            notes.append("no Teams transcript available")
    except Exception as e:
        log.exception("Transcript fetch failed for meeting=%s", meeting_id)
        notes.append(f"transcript fetch failed: {e}")

    participants: list[str] | None = None
    attendance_imported = False
    try:
        reports = msgraph.list_attendance_reports(db, acct, meeting_id)
        if reports:
            rid = reports[0].get("id")
            records = msgraph.get_attendance_records(db, acct, meeting_id, rid)
            participants = msgraph.names_from_attendance(records) or None
            attendance_imported = bool(participants)
        else:
            notes.append("no attendance report available")
    except Exception as e:
        log.exception("Attendance fetch failed for meeting=%s", meeting_id)
        notes.append(f"attendance fetch failed: {e}")

    if not participants:
        organizer = ((meeting.get("participants") or {}).get("organizer") or {})
        attendees = (meeting.get("participants") or {}).get("attendees") or []
        names: list[str] = []
        for p in [organizer, *attendees]:
            upn = ((p.get("upn") or "") if isinstance(p, dict) else "")
            ident = ((p.get("identity") or {}) if isinstance(p, dict) else {})
            user_ident = (ident.get("user") or {})
            name = user_ident.get("displayName") or upn
            if name and name not in names:
                names.append(name)
        participants = names or None

    job = AudioJob(
        id=job_id,
        user_id=current.id,
        original_filename=stored_name,
        stored_filename=stored_name,
        file_path=file_path,
        mime_type="video/mp4",
        size_bytes=size_bytes,
        status=JobStatus.queued,
        diarize=payload.diarize,
        title=(payload.title or subject)[:512],
        project=(payload.project or None),
        meeting_date=meeting_date,
        participants=participants,
        source="teams",
        source_meeting_id=meeting_id,
        teams_transcript_vtt=transcript_vtt,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        enqueue_job(job.id)
    except Exception as e:
        log.exception("Failed to enqueue imported Teams job %s", job.id)
        job.status = JobStatus.failed
        job.error_message = f"enqueue failed: {e}"
        db.commit()
        raise HTTPException(status_code=500, detail="failed to enqueue processing")

    return TeamsImportResponse(
        job_id=job.id,
        status=job.status,
        recording_downloaded=recording_downloaded,
        transcript_imported=transcript_imported,
        attendance_imported=attendance_imported,
        notes=notes,
    )
