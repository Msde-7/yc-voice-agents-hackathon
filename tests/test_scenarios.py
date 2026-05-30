"""Tests for call scenarios."""

import pytest
from scenarios import SCENARIOS


def test_all_scenarios_present():
    expected = {"general_support", "hours_inquiry", "refund_request", "appointment_booking", "product_question"}
    assert set(SCENARIOS.keys()) == expected


def test_all_scenarios_have_required_fields():
    for scenario_id, scenario in SCENARIOS.items():
        assert scenario["id"] == scenario_id, f"{scenario_id}: id mismatch"
        assert scenario["name"], f"{scenario_id}: name is empty"
        assert scenario["description"], f"{scenario_id}: description is empty"
        assert scenario["system_prompt"], f"{scenario_id}: system_prompt is empty"


def test_scenario_prompts_mention_phone_context():
    phone_keywords = {"phone", "call", "conversational", "short"}
    for scenario_id, scenario in SCENARIOS.items():
        prompt_lower = scenario["system_prompt"].lower()
        assert any(kw in prompt_lower for kw in phone_keywords), (
            f"{scenario_id}: system_prompt should reference phone/call context"
        )


def test_scenario_prompts_have_single_opening_question():
    """Each prompt should direct the agent to open with a single question, not a list."""
    for scenario_id, scenario in SCENARIOS.items():
        prompt_lower = scenario["system_prompt"].lower()
        # Prompt should not enumerate multiple things to ask in one turn
        assert "ask about" not in prompt_lower or "ask about their" in prompt_lower, (
            f"{scenario_id}: prompt should not list multiple topics to ask about at once"
        )
        assert prompt_lower.count("and if they") == 0, (
            f"{scenario_id}: prompt should not chain questions with 'and if they'"
        )
