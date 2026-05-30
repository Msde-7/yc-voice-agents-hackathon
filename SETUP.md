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
# Copy the https://xxxx.ngrok.io URL — you'll need it below
```

### Start the server (terminal 2)

```bash
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Trigger a call (terminal 3)

```bash
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567"}'
```

Replace `+15551234567` with the business phone number to call.

**Note:** Twilio will POST to `https://xxxx.ngrok.io/twiml` when the call connects. The TwiML response streams audio to `wss://xxxx.ngrok.io/ws`, where the Pipecat pipeline handles the conversation.

## 6. Architecture

```
POST /call → Twilio REST API (outbound call)
                ↓
Twilio dials target → POST /twiml (webhook)
                ↓
TwiML: <Stream url="wss://host/ws" />
                ↓
WebSocket /ws → Pipecat Pipeline:
  Twilio Input → NVIDIA ASR (STT) → Nemotron LLM → Gradium TTS → Twilio Output
```

## Key Files

| File | Purpose |
|---|---|
| `server/main.py` | FastAPI app — `/call`, `/twiml`, `/ws` endpoints |
| `server/bot.py` | Pipecat pipeline definition |
| `server/nvidia_stt.py` | NVIDIA WebSocket STT service |
| `server/nemotron_llm.py` | NVIDIA Nemotron (vLLM) LLM service |
| `pyproject.toml` | Python project & dependency config |
| `.env.example` | Template for all required environment variables |
