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

You MUST output a JSON object with a single key "scenarios" whose value is an array of exactly {count} objects.
Each object must have these exact keys:
- "id": snake_case string identifier
- "name": short display name
- "description": one sentence describing what this scenario tests
- "system_prompt": full system prompt for the AI customer agent — must (1) set up a specific realistic customer persona with a concrete goal, (2) include relevant details like student ID, dates, or context where appropriate, (3) instruct the agent to speak in very short turns — one sentence at a time, ask one question then wait, never list multiple questions at once, (4) end with: "Once you have what you need, say a brief thanks and call the end_call function to hang up. Do NOT say 'end call' out loud."

Example output format (do not copy content, only structure):
{{"scenarios": [{{"id": "example_id", "name": "Example", "description": "Tests X.", "system_prompt": "You are..."}}]}}"""


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
        logger.debug(f"Parsed scenario JSON type: {type(parsed).__name__}, keys/len: {list(parsed.keys()) if isinstance(parsed, dict) else len(parsed)}")

        # Normalise to a flat list of scenario dicts regardless of what the model returned
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            # Check if it looks like a single scenario (has id + system_prompt at top level)
            if "system_prompt" in parsed and "id" in parsed:
                items = [parsed]
            else:
                # Find the first value that is a list of dicts
                items = None
                for v in parsed.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        items = v
                        break
                if items is None:
                    # Dict of scenario dicts keyed by id or index: {"0": {...}, "admissions": {...}}
                    items = [v for v in parsed.values() if isinstance(v, dict)]
        else:
            raise ValueError(f"Unexpected top-level JSON type: {type(parsed)}")

        scenarios: dict[str, Scenario] = {}
        for item in items:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict item in scenario list: {type(item)}")
                continue
            sid = item.get("id", f"scenario_{len(scenarios)}")
            scenarios[sid] = Scenario(
                id=sid,
                name=item.get("name", sid),
                description=item.get("description", ""),
                system_prompt=item.get("system_prompt", ""),
            )

        if not scenarios:
            raise ValueError("LLM returned empty scenarios list")

        logger.info(f"Generated scenarios: {list(scenarios.keys())}")
        return scenarios

    except Exception as e:
        logger.error(f"Scenario generation failed: {e} — falling back to defaults")
        return SCENARIOS
