from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ..models.audio_job import JobStatus


class AudioJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    size_bytes: int
    duration_seconds: float | None
    mime_type: str | None
    status: JobStatus
    progress: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AudioJobListOut(BaseModel):
    items: list[AudioJobOut]
    total: int


class UploadResponse(BaseModel):
    job_id: UUID
    status: JobStatus
