"""In-memory store for multi-scenario analysis sessions."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from report_models import CallReport


class AnalysisRecord(BaseModel):
    id: str
    to_number: str
    website: str | None = None
    business_context: str | None = None
    scenarios: list[str]
    status: Literal["running", "completed", "failed"]
    call_sids: list[str] = []
    report: CallReport | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


_store: dict[str, AnalysisRecord] = {}


def create(to_number: str, scenarios: list[str], website: str | None = None) -> AnalysisRecord:
    record = AnalysisRecord(
        id=str(uuid.uuid4()),
        to_number=to_number,
        website=website,
        scenarios=scenarios,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    _store[record.id] = record
    return record


def update(id: str, **kwargs) -> None:
    record = _store.get(id)
    if record:
        _store[id] = record.model_copy(update=kwargs)


def get(id: str) -> AnalysisRecord | None:
    return _store.get(id)


def list_all() -> list[AnalysisRecord]:
    return list(_store.values())
