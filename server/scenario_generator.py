"""Generates tailored call scenarios for a specific business using Nemotron."""

import json
import os
from typing import Any

import aiohttp
from loguru import logger

from scenarios import SCENARIOS, Scenario

_SYSTEM_PROMPT = """\
You are an expert in customer support call testing for AI voice agents.
Given a description of a business, generate realistic customer call scenarios
that would test their support capabilities across different interaction types.
Respond ONLY with valid JSON — no explanation, no markdown."""

_USER_PROMPT = """\
Business context:
{context}

Generate exactly {count} customer call scenarios for testing this business's phone support.
Each scenario should represent a realistic customer need specific to this type of business.
Cover a mix of: simple information requests, service bookings, complaints/issues, and product/pricing questions.

Output a JSON array with exactly {count} objects, each with this structure:
{{
  "id": "snake_case_identifier",
  "name": "Short Display Name",
  "description": "One sentence describing what this scenario tests.",
  "system_prompt": "Full system prompt for the AI customer agent. Must: (1) set up a specific, realistic customer persona with a concrete goal, (2) include relevant details like order numbers, dates, or context where appropriate, (3) instruct the agent to keep responses short and conversational since this is a phone call, (4) end with: Once you have gathered enough information about how this business handles your request, say a brief thank you, then call the end_call function to hang up. Do NOT say 'end call' out loud — just call the function."
}}"""


async def generate_scenarios(business_context: str, count: int = 5) -> dict[str, Scenario]:
    """Generate tailored call scenarios for the given business context.

    Falls back to the static default scenarios if generation fails.
    """
    if not business_context.strip():
        logger.warning("No business context — using default scenarios")
        return SCENARIOS

    llm_url = os.environ["NEMOTRON_LLM_URL"]
    model = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")

    prompt = _USER_PROMPT.format(context=business_context[:4000], count=count)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "max_tokens": 3000,
    }

    logger.info(f"Generating {count} tailored scenarios via Nemotron")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{llm_url}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer not-needed"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        raw = data["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()

        parsed: Any = json.loads(raw)

        # Model may return {"scenarios": [...]} or a bare list
        if isinstance(parsed, dict):
            items = next(iter(parsed.values()))
        else:
            items = parsed

        scenarios: dict[str, Scenario] = {}
        for item in items:
            sid = item["id"]
            scenarios[sid] = Scenario(
                id=sid,
                name=item["name"],
                description=item["description"],
                system_prompt=item["system_prompt"],
            )

        if not scenarios:
            raise ValueError("LLM returned empty scenarios list")

        logger.info(f"Generated scenarios: {list(scenarios.keys())}")
        return scenarios

    except Exception as e:
        logger.error(f"Scenario generation failed: {e} — falling back to defaults")
        return SCENARIOS
