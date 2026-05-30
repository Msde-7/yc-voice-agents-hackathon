"""In-memory call record store."""

from datetime import datetime, timezone

from models import CallRecord

_store: dict[str, CallRecord] = {}


def create(call_sid: str, to_number: str, scenario_id: str) -> CallRecord:
    record = CallRecord(
        call_sid=call_sid,
        to_number=to_number,
        scenario_id=scenario_id,
        status="initiated",
        started_at=datetime.now(timezone.utc),
    )
    _store[call_sid] = record
    return record


def update_status(
    call_sid: str,
    status: str,
    ended_at: datetime | None = None,
    transcript: list[dict] | None = None,
) -> None:
    record = _store.get(call_sid)
    if not record:
        return
    _store[call_sid] = record.model_copy(
        update={
            "status": status,
            **({"ended_at": ended_at} if ended_at is not None else {}),
            **({"transcript": transcript} if transcript is not None else {}),
        }
    )


def get(call_sid: str) -> CallRecord | None:
    return _store.get(call_sid)


def list_all() -> list[CallRecord]:
    return list(_store.values())


def list_by_number(to_number: str) -> list[CallRecord]:
    return [r for r in _store.values() if r.to_number == to_number]
