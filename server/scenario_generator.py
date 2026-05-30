"""Generates tailored call scenarios for a specific business using Nemotron structured output."""

import json
import os

import aiohttp
from loguru import logger

from scenarios import SCENARIOS, Scenario

_SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "system_prompt": {"type": "string"},
                },
                "required": ["id", "name", "description", "system_prompt"],
            },
        }
    },
    "required": ["scenarios"],
}

_SYSTEM_PROMPT = """\
You are an expert in customer support call testing for AI voice agents.
Given a description of a business, generate realistic customer call scenarios
that test their support capabilities across different interaction types."""

_USER_PROMPT = """\
Business context:
{context}

Generate exactly {count} customer call scenarios for testing this business's phone support.
Cover a mix of: simple information requests, service bookings, complaints/issues, and pricing questions.

For each scenario:
- id: short snake_case identifier
- name: short display name
- description: one sentence describing what this scenario tests
- system_prompt: 2-3 sentences. Set up a specific customer persona with a concrete goal \
relevant to this business. Instruct the agent to ask one question at a time and wait for \
the answer before asking the next. End with: "Only call end_call after several exchanges. \
Do NOT say end call aloud.\""""


async def generate_scenarios(business_context: str, count: int = 3) -> dict[str, Scenario]:
    """Generate tailored call scenarios for the given business context.

    Uses json_schema structured output to guarantee the response matches the
    expected shape. Falls back to the static default scenarios if generation fails.
    """
    if not business_context.strip():
        logger.warning("No business context — using default scenarios")
        return SCENARIOS

    llm_url = os.environ["NEMOTRON_LLM_URL"]
    model = os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT.format(context=business_context[:4000], count=count)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "scenarios", "schema": _SCENARIO_SCHEMA},
        },
        "temperature": 0.7,
        "max_tokens": 2048,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    logger.info(f"Generating {count} tailored scenarios via Nemotron (structured output)")

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

        items = json.loads(data["choices"][0]["message"]["content"])["scenarios"][:count]

        scenarios: dict[str, Scenario] = {
            item["id"]: Scenario(
                id=item["id"],
                name=item["name"],
                description=item["description"],
                system_prompt=item["system_prompt"],
            )
            for item in items
        }

        if not scenarios:
            raise ValueError("Model returned empty scenarios list")

        logger.info(f"Generated scenarios: {list(scenarios.keys())}")
        return scenarios

    except Exception as e:
        logger.error(f"Scenario generation failed: {e} — falling back to defaults")
        return SCENARIOS
