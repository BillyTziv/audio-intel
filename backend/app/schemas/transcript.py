from typing import Any

from pydantic import BaseModel, ConfigDict


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str | None
    raw_text: str | None
    cleaned_text: str | None
    summary: str | None
    key_points: list[Any] | None
    decisions: list[Any] | None
    action_items: list[Any] | None
    segments: list[Any] | None
