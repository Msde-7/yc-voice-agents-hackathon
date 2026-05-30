"""Tests for report generation — mocks the LLM call to avoid network dependency."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import CallRecord
from report_models import CallReport


def _make_record(sid="CA123", scenario="hours_inquiry", transcript=None) -> CallRecord:
    return CallRecord(
        call_sid=sid,
        to_number="+15551234567",
        scenario_id=scenario,
        status="completed",
        started_at=datetime.now(timezone.utc),
        transcript=transcript or [
            {"role": "user", "content": "What are your hours?"},
            {"role": "assistant", "content": "We are open 9am to 5pm weekdays."},
        ],
    )


def _mock_session(payload: dict):
    resp = MagicMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps(payload)}}]
    })
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=resp)
    return session


VALID_REPORT_PAYLOAD = {
    "automation_score": 0.9,
    "flow_steps": [
        {
            "topic": "business hours inquiry",
            "can_automate": True,
            "confidence": 0.95,
            "reasoning": "Straightforward lookup from schedule database.",
            "example_quote": "What are your hours?",
        }
    ],
    "summary": "The call was a simple hours inquiry, fully automatable.",
    "recommended_actions": ["Deploy an IVR for hours inquiries."],
}


@pytest.mark.asyncio
async def test_generate_report_happy_path():
    """Valid LLM response produces a correct CallReport."""
    import os
    os.environ.setdefault("NEMOTRON_LLM_URL", "http://dummy")

    with patch("aiohttp.ClientSession", return_value=_mock_session(VALID_REPORT_PAYLOAD)):
        from report import generate_report
        report = await generate_report([_make_record()])

    assert isinstance(report, CallReport)
    assert report.automation_score == 0.9
    assert len(report.flow_steps) == 1
    assert report.flow_steps[0].can_automate is True
    assert report.flow_steps[0].confidence == 0.95
    assert report.summary
    assert report.call_sids == ["CA123"]
    assert report.scenarios_tested == ["hours_inquiry"]


@pytest.mark.asyncio
async def test_generate_report_no_transcripts_raises():
    """Records with no transcripts raise ValueError."""
    from report import generate_report
    record = _make_record(transcript=None)
    record.transcript = None
    with pytest.raises(ValueError, match="No completed calls"):
        await generate_report([record])


@pytest.mark.asyncio
async def test_generate_report_multiple_records():
    """Report aggregates call_sids and scenarios_tested from multiple records."""
    import os
    os.environ.setdefault("NEMOTRON_LLM_URL", "http://dummy")

    records = [
        _make_record("CA1", "hours_inquiry"),
        _make_record("CA2", "refund_request"),
    ]

    with patch("aiohttp.ClientSession", return_value=_mock_session(VALID_REPORT_PAYLOAD)):
        from report import generate_report
        report = await generate_report(records)

    assert set(report.call_sids) == {"CA1", "CA2"}
    assert set(report.scenarios_tested) == {"hours_inquiry", "refund_request"}
