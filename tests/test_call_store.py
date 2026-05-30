"""Tests for the in-memory call store."""

import importlib
from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def reset_store():
    """Reset call_store state between tests."""
    import call_store
    call_store._store.clear()
    yield
    call_store._store.clear()


def test_create_and_retrieve():
    import call_store
    record = call_store.create("CA001", "+15551111111", "hours_inquiry")
    assert record.call_sid == "CA001"
    assert record.to_number == "+15551111111"
    assert record.scenario_id == "hours_inquiry"
    assert record.status == "initiated"
    assert record.transcript is None

    fetched = call_store.get("CA001")
    assert fetched is not None
    assert fetched.call_sid == "CA001"


def test_update_status():
    import call_store
    call_store.create("CA002", "+15552222222", "refund_request")
    call_store.update_status("CA002", "in_progress")
    assert call_store.get("CA002").status == "in_progress"

    ended = datetime.now(timezone.utc)
    msgs = [{"role": "user", "content": "hi"}]
    call_store.update_status("CA002", "completed", ended_at=ended, transcript=msgs)
    record = call_store.get("CA002")
    assert record.status == "completed"
    assert record.ended_at == ended
    assert record.transcript == msgs


def test_list_returns_all_records():
    import call_store
    call_store.create("CA003", "+15553333333", "general_support")
    call_store.create("CA004", "+15554444444", "appointment_booking")
    records = call_store.list_all()
    sids = {r.call_sid for r in records}
    assert {"CA003", "CA004"}.issubset(sids)


def test_get_unknown_sid_returns_none():
    import call_store
    assert call_store.get("CA_DOES_NOT_EXIST") is None


def test_update_unknown_sid_is_noop():
    import call_store
    call_store.update_status("CA_GHOST", "completed")  # should not raise
