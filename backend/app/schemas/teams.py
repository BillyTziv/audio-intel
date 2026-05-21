from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from ..models.audio_job import JobStatus


class TeamsConnectionStatus(BaseModel):
    connected: bool
    ms_display_name: str | None = None
    ms_user_principal_name: str | None = None
    token_expires_at: datetime | None = None


class TeamsAuthStartResponse(BaseModel):
    authorize_url: str
    state: str


class TeamsMeetingSummary(BaseModel):
    event_id: str
    subject: str | None
    start: datetime | None
    end: datetime | None
    organizer: str | None
    join_url: str
    web_link: str | None
    attendees: list[str]


class TeamsMeetingListOut(BaseModel):
    items: list[TeamsMeetingSummary]


class TeamsImportRequest(BaseModel):
    join_url: str
    diarize: bool = False
    title: str | None = None
    project: str | None = None


class TeamsImportResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    recording_downloaded: bool
    transcript_imported: bool
    attendance_imported: bool
    notes: list[str]
