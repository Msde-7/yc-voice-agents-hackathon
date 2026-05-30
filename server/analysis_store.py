"""In-memory store for multi-scenario analysis sessions."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from report_models import CallReport

# Maps analysis_id → running asyncio.Task (not serialised — in-process only)
_tasks: dict[str, "asyncio.Task"] = {}  # type: ignore[name-defined]


class AnalysisRecord(BaseModel):
    id: str
    to_number: str
    website: str | None = None
    business_context: str | None = None
    scenarios: list[str]
    status: Literal["running", "completed", "failed", "cancelled"]
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


def register_task(id: str, task: "asyncio.Task") -> None:  # type: ignore[name-defined]
    _tasks[id] = task


def cancel(id: str) -> bool:
    """Cancel a running analysis. Returns True if a task was found and cancelled."""
    task = _tasks.pop(id, None)
    if task and not task.done():
        task.cancel()
        update(id, status="cancelled", completed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        return True
    update(id, status="cancelled", completed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    return False
