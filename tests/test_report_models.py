"""Tests for report Pydantic models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from report_models import CallReport, FlowStep


def _make_report(**overrides) -> dict:
    base = {
        "generated_at": datetime.now(timezone.utc),
        "call_sids": ["CA123"],
        "scenarios_tested": ["hours_inquiry"],
        "automation_score": 0.75,
        "flow_steps": [
            FlowStep(
                topic="hours inquiry",
                can_automate=True,
                confidence=0.9,
                reasoning="Straightforward lookup — no human judgment required.",
                example_quote="What are your hours?",
            )
        ],
        "summary": "Most of the support flow is automatable.",
        "recommended_actions": ["Deploy IVR for hours"],
    }
    base.update(overrides)
    return base


def test_valid_report_construction():
    report = CallReport(**_make_report())
    assert report.automation_score == 0.75
    assert len(report.flow_steps) == 1
    assert report.flow_steps[0].can_automate is True


def test_automation_score_bounds():
    CallReport(**_make_report(automation_score=0.0))
    CallReport(**_make_report(automation_score=1.0))
    with pytest.raises(ValidationError):
        CallReport(**_make_report(automation_score=1.1))
    with pytest.raises(ValidationError):
        CallReport(**_make_report(automation_score=-0.1))


def test_flow_step_confidence_bounds():
    FlowStep(topic="t", can_automate=True, confidence=0.0, reasoning="r")
    FlowStep(topic="t", can_automate=True, confidence=1.0, reasoning="r")
    with pytest.raises(ValidationError):
        FlowStep(topic="t", can_automate=True, confidence=1.5, reasoning="r")
    with pytest.raises(ValidationError):
        FlowStep(topic="t", can_automate=True, confidence=-0.1, reasoning="r")


def test_optional_example_quote():
    step = FlowStep(topic="t", can_automate=False, confidence=0.5, reasoning="r")
    assert step.example_quote is None

    step_with_quote = FlowStep(
        topic="t", can_automate=False, confidence=0.5,
        reasoning="r", example_quote="Can I get a refund?"
    )
    assert step_with_quote.example_quote == "Can I get a refund?"


def test_report_multiple_flow_steps():
    steps = [
        FlowStep(topic="hours", can_automate=True, confidence=0.95, reasoning="simple"),
        FlowStep(topic="refund", can_automate=False, confidence=0.8, reasoning="needs empathy"),
    ]
    report = CallReport(**_make_report(flow_steps=steps))
    assert len(report.flow_steps) == 2
