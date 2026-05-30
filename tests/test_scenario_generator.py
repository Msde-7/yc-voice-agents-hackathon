"""Tests for scenario_generator — mocks the LLM call to avoid network dependency."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scenarios import SCENARIOS


@pytest.fixture
def mock_response_factory():
    """Build a mock aiohttp response with given JSON content."""
    def _make(payload: dict):
        content_str = json.dumps(payload)
        resp = MagicMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.raise_for_status = MagicMock()
        resp.json = AsyncMock(return_value={
            "choices": [{"message": {"content": content_str}}]
        })
        return resp
    return _make


@pytest.fixture
def mock_session_factory(mock_response_factory):
    """Build a mock aiohttp.ClientSession for a given payload."""
    def _make(payload: dict):
        resp = mock_response_factory(payload)
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.post = MagicMock(return_value=resp)
        return session
    return _make


VALID_PAYLOAD = {
    "scenarios": [
        {
            "id": "admissions_inquiry",
            "name": "Admissions Inquiry",
            "description": "Tests ability to provide admissions info.",
            "system_prompt": "You are a prospective student. Ask about deadlines. Ask one question at a time. Only call end_call after several exchanges.",
        },
        {
            "id": "financial_aid_issue",
            "name": "Financial Aid Issue",
            "description": "Tests handling of missing aid disbursement.",
            "system_prompt": "You are a student missing financial aid. Ask about it. Ask one question at a time. Only call end_call after several exchanges.",
        },
    ]
}


@pytest.mark.asyncio
async def test_generate_scenarios_happy_path(mock_session_factory):
    """Valid LLM response produces correct Scenario dicts."""
    import os
    os.environ.setdefault("NEMOTRON_LLM_URL", "http://dummy")

    with patch("aiohttp.ClientSession", return_value=mock_session_factory(VALID_PAYLOAD)):
        from scenario_generator import generate_scenarios
        result = await generate_scenarios("Northeastern University, Boston.", count=2)

    assert len(result) == 2
    for sid, s in result.items():
        assert s["id"] == sid
        assert s["name"]
        assert s["description"]
        assert s["system_prompt"]


@pytest.mark.asyncio
async def test_generate_scenarios_empty_context_returns_defaults():
    """Empty business context returns static default scenarios without calling LLM."""
    from scenario_generator import generate_scenarios
    result = await generate_scenarios("", count=3)
    assert result is SCENARIOS


@pytest.mark.asyncio
async def test_generate_scenarios_respects_count(mock_session_factory):
    """Result is capped to requested count even if model returns more."""
    import os
    os.environ.setdefault("NEMOTRON_LLM_URL", "http://dummy")

    # Payload has 2 scenarios, but we request 1
    with patch("aiohttp.ClientSession", return_value=mock_session_factory(VALID_PAYLOAD)):
        from scenario_generator import generate_scenarios
        result = await generate_scenarios("Northeastern University.", count=1)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_generate_scenarios_falls_back_on_llm_error():
    """LLM network error returns static default scenarios."""
    import os
    os.environ.setdefault("NEMOTRON_LLM_URL", "http://dummy")

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=Exception("network error"))

    with patch("aiohttp.ClientSession", return_value=session):
        from scenario_generator import generate_scenarios
        result = await generate_scenarios("Some business.", count=3)

    assert result is SCENARIOS
