"""Shared Pydantic models for Gunk."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CallRecord(BaseModel):
    call_sid: str
    to_number: str
    scenario_id: str
    status: Literal["initiated", "in_progress", "completed", "failed"]
    started_at: datetime
    ended_at: datetime | None = None
    transcript: list[dict] | None = None
