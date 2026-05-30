"""Generates automation analysis reports from completed call transcripts using Nemotron structured output."""

import json
import os
from datetime import datetime, timezone

import aiohttp
from loguru import logger

from models import CallRecord
from report_models import CallReport, FlowStep

_REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "automation_score": {"type": "number"},
        "flow_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "can_automate": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "example_quote": {"type": "string"},
                },
                "required": ["topic", "can_automate", "confidence", "reasoning"],
            },
        },
        "summary": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["automation_score", "flow_steps", "summary", "recommended_actions"],
}

_SYSTEM_PROMPT = """\
You are an expert in AI voice agent automation for customer support operations.
Analyze call transcripts to identify which parts of a business's support flow
could be handled by an AI voice agent versus which require a human."""

_USER_PROMPT = """\
Analyze these call transcripts from Gunk, a platform that simulates customer calls \
to test a business's phone support.

For each topic or interaction type you identify, assess whether an AI voice agent could \
reliably handle it (can_automate=true) or whether it requires human judgment \
(can_automate=false).

Rules:
- Automatable: clear factual answers, information lookup, simple scheduling
- Human needed: complex negotiation, empathy-heavy situations, policy exceptions

Compute automation_score (0.0–1.0) as the fraction of the support flow that could be automated.

TRANSCRIPTS:
{transcripts}"""

_MAX_TRANSCRIPT_CHARS = 1500


def _format_transcript(record: CallRecord) -> str:
    """Format a call record's messages into readable text for the LLM."""
    lines = [f"--- Scenario: {record.scenario_id} ---"]
    for msg in record.transcript or []:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if content and role != "SYSTEM":
            lines.append(f"{role}: {content}")
    text = "\n".join(lines)
    return text[:_MAX_TRANSCRIPT_CHARS] + "\n[truncated]" if len(text) > _MAX_TRANSCRIPT_CHARS else text


async def generate_report(records: list[CallRecord]) -> CallReport:
    """Analyze completed call transcripts and return an automation report.

    Uses json_schema structured output to guarantee the response matches CallReport.
    """
    usable = [r for r in records if r.transcript]
    if not usable:
        raise ValueError("No completed calls with transcripts available for analysis")

    transcripts_text = "\n\n".join(_format_transcript(r) for r in usable)

    llm_url = os.environ["NEMOTRON_LLM_URL"]
    model = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(transcripts=transcripts_text)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "report", "schema": _REPORT_SCHEMA},
        },
        "temperature": 0.2,
        "max_tokens": 2048,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    logger.info(f"Generating report for {len(usable)} call(s) via {llm_url} (structured output)")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{llm_url}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer not-needed"},
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

    result = json.loads(data["choices"][0]["message"]["content"])

    return CallReport(
        generated_at=datetime.now(timezone.utc),
        call_sids=[r.call_sid for r in usable],
        scenarios_tested=list({r.scenario_id for r in usable}),
        automation_score=result["automation_score"],
        flow_steps=[FlowStep(**step) for step in result["flow_steps"]],
        summary=result["summary"],
        recommended_actions=result["recommended_actions"],
    )
