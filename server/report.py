"""Generates automation analysis reports from completed call transcripts using Nemotron."""

import json
import os
from datetime import datetime, timezone

import aiohttp
from loguru import logger

from models import CallRecord
from report_models import CallReport

_ANALYSIS_SCHEMA = json.dumps(
    {
        "generated_at": "<ISO 8601 datetime>",
        "call_sids": ["<call SID>"],
        "scenarios_tested": ["<scenario name>"],
        "automation_score": 0.0,
        "flow_steps": [
            {
                "topic": "<topic>",
                "can_automate": True,
                "confidence": 0.0,
                "reasoning": "<why>",
                "example_quote": "<optional verbatim quote from transcript>",
            }
        ],
        "summary": "<2-3 sentence summary>",
        "recommended_actions": ["<action>"],
    },
    indent=2,
)

_SYSTEM_PROMPT = """\
You are an expert in AI voice agent automation for customer support operations.
You analyze call transcripts to identify which parts of a business's support flow
could be handled by an AI voice agent versus which parts require a human.

Respond ONLY with valid JSON matching the exact schema provided. No explanation, no markdown."""

_USER_PROMPT_TEMPLATE = """\
Analyze the following call transcripts from Gunk — a platform that simulates customer calls
to test a business's support experience.

For each topic or interaction type you identify across all calls, assess whether an AI voice
agent could reliably handle it (can_automate=true) or whether it requires human judgment
(can_automate=false). Consider: clear rules-based answers, information retrieval, simple
scheduling = automatable. Complex negotiation, empathy-heavy situations, edge cases,
policy exceptions = human needed.

Compute an overall automation_score (0.0–1.0) representing the fraction of the support
flow that could be automated.

TRANSCRIPTS:
{transcripts}

CALLS ANALYZED:
{call_summary}

Respond with JSON matching this schema exactly:
{schema}
"""


def _format_transcript(record: CallRecord) -> str:
    lines = [f"--- Call {record.call_sid} | Scenario: {record.scenario_id} ---"]
    for msg in (record.transcript or []):
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if content and role != "SYSTEM":
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def generate_report(records: list[CallRecord]) -> CallReport:
    """Analyze completed call transcripts and return an automation report."""
    usable = [r for r in records if r.transcript]
    if not usable:
        raise ValueError("No completed calls with transcripts available for analysis")

    transcripts_text = "\n\n".join(_format_transcript(r) for r in usable)
    call_summary = "\n".join(
        f"- {r.call_sid}: scenario={r.scenario_id}, status={r.status}"
        for r in usable
    )

    prompt = _USER_PROMPT_TEMPLATE.format(
        transcripts=transcripts_text,
        call_summary=call_summary,
        schema=_ANALYSIS_SCHEMA,
    )

    llm_url = os.environ["NEMOTRON_LLM_URL"]
    model = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    logger.info(f"Generating report for {len(usable)} call(s) via {llm_url}")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{llm_url}/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer not-needed"},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

    raw = data["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}\nRaw: {raw[:500]}")
        raise ValueError(f"Report generation failed: LLM returned invalid JSON") from e

    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    parsed["call_sids"] = [r.call_sid for r in usable]
    parsed["scenarios_tested"] = list({r.scenario_id for r in usable})

    return CallReport.model_validate(parsed)
