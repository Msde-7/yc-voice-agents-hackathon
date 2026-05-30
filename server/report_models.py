"""Pydantic models for Gunk analysis reports."""

from datetime import datetime

from pydantic import BaseModel, Field


class FlowStep(BaseModel):
    topic: str
    can_automate: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    example_quote: str | None = None


class CallReport(BaseModel):
    generated_at: datetime
    call_sids: list[str]
    scenarios_tested: list[str]
    automation_score: float = Field(ge=0.0, le=1.0)
    flow_steps: list[FlowStep]
    summary: str
    recommended_actions: list[str]
