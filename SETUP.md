# Gunk — Setup Guide

## Prerequisites

- Python 3.12+ (minimum; 3.14 is current as of 2026 — any 3.12+ works)
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- Node.js 20+ (for Twilio CLI)
- A publicly reachable server URL for Twilio webhooks (use [ngrok](https://ngrok.com/) for local dev)

## 1. Python Dependencies

```bash
uv sync
```

This installs all dependencies into `.venv` using `pyproject.toml`.

## 2. Environment Variables

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

| Variable | Where to get it |
|---|---|
| `TWILIO_ACCOUNT_SID` | [console.twilio.com](https://console.twilio.com) → Account Info |
| `TWILIO_AUTH_TOKEN` | Same page as above |
| `TWILIO_PHONE_NUMBER` | Twilio Console → Phone Numbers (must be voice-capable) |
| `GRADIUM_API_KEY` | [gradium.ai](https://gradium.ai) — hackathon credits provided at event |
| `GRADIUM_VOICE_ID` | Gradium dashboard — optional, defaults to `Eu9iL_CYe8N-Gkx_` |
| `NVIDIA_ASR_URL` | Hackathon-provided: `ws://44.241.251.184:8080` |
| `NEMOTRON_LLM_URL` | Hackathon-provided: `http://nemotron-fleet-alb-1322439314.us-west-2.elb.amazonaws.com/v1` |
| `NEMOTRON_LLM_MODEL` | Optional — defaults to `nvidia/nemotron-3-super` |
| `NEMOTRON_ENABLE_THINKING` | `False` (keep off for voice — thinking tokens get spoken aloud) |
| `CEKURA_API_KEY` | [dashboard.cekura.ai](https://dashboard.cekura.ai) |
| `CEKURA_AGENT_ID` | Cekura dashboard → your agent → integer ID |
| `FIRECRAWL_API_KEY` | [firecrawl.dev](https://www.firecrawl.dev) — used for business website scraping |
| `PUBLIC_BASE_URL` | Your ngrok URL (e.g. `https://xxxx.ngrok-free.app`) — required when using the frontend at `localhost`, so Twilio can reach the webhook |

## 3. Twilio CLI

```bash
# Install (already done if npm is available)
npm install -g twilio-cli

# Authenticate
twilio login
# Enter Account SID and Auth Token when prompted
```

## 4. Cekura (evaluation)

The Cekura plugin is pre-registered in `.claude/settings.json` and will install automatically when Claude Code loads this project. No manual install needed.

To also add the Cekura MCP server for direct API access:

```bash
claude mcp add --transport http Cekura https://api.cekura.ai/mcp \
  --header "X-CEKURA-API-KEY:YOUR_API_KEY"
```

## 5. Running Locally

### Start ngrok (terminal 1)

Twilio needs a public URL to POST webhooks. Run ngrok to expose the local server:

```bash
ngrok http 8000
# Copy the https://xxxx.ngrok.io URL
```

### Start the server (terminal 2)

On Windows, set UTF-8 encoding to avoid emoji errors in Pipecat's startup message:

```bash
cd server
PYTHONUTF8=1 uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Run a full multi-scenario analysis (terminal 3)

```bash
# Gunk scrapes the business, generates tailored scenarios, calls sequentially,
# and auto-produces a report when all calls complete.
curl -X POST https://xxxx.ngrok.io/analyze \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567"}'

# Returns {"id": "...", "status": "running", ...}
# Poll until status == "completed":
curl https://xxxx.ngrok.io/analyze/{id}
```

### Single call (optional, for testing one scenario)

```bash
curl -X POST https://xxxx.ngrok.io/call \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567", "scenario": "hours_inquiry"}'
```

### Local browser test (no Twilio needed)

```bash
cd server
PYTHONUTF8=1 uv run bot_local.py
# Open http://localhost:7860 in Chrome and click Connect
```

## 6. Architecture

```
POST /analyze (to, optional website)
        ↓
Firecrawl: search phone number → scrape business website
        ↓
Nemotron: generate N tailored call scenarios
        ↓
For each scenario (sequential, 5s gap):
  Twilio dials business → POST /twiml → WebSocket /ws
        ↓
  Pipecat Pipeline:
    Twilio In → Gradium STT → Nemotron LLM → Gradium TTS → Twilio Out
        ↓
  Call ends → transcript saved → Cekura observability
        ↓
All scenarios complete → Nemotron analyzes transcripts
        ↓
CallReport: flow_steps, automation_score, recommended_actions
```

## Key Files

| File | Purpose |
|---|---|
| `server/main.py` | FastAPI app — all HTTP endpoints |
| `server/bot.py` | Pipecat pipeline (Twilio phone calls) |
| `server/bot_local.py` | Pipecat pipeline (local WebRTC browser test) |
| `server/business_context.py` | Firecrawl scraping — finds business website by phone number |
| `server/scenario_generator.py` | Generates tailored call personas via Nemotron |
| `server/scenarios.py` | Static fallback scenarios |
| `server/report.py` | Generates automation report from transcripts via Nemotron |
| `server/call_store.py` | In-memory call record store |
| `server/analysis_store.py` | In-memory analysis session store |
| `server/nemotron_llm.py` | NVIDIA Nemotron (vLLM) LLM service |
| `server/nvidia_stt.py` | NVIDIA WebSocket STT service (unused in phone flow; for future use) |
| `pyproject.toml` | Python project & dependency config |
| `.env.example` | Template for all required environment variables |
