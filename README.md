# Gunk

Gunk calls a business's phone number, acts as different types of customers, and produces a report showing which parts of their support flow could be handled by an AI voice agent — and which need a human.

## Architecture

```
POST /call (scenario) → Twilio REST API (outbound call)
                ↓
  Twilio dials target → POST /twiml (webhook)
                ↓
  TwiML: <Stream url="wss://host/ws" />
                ↓
  WebSocket /ws → Pipecat Pipeline:
    Twilio In → NVIDIA ASR → Nemotron LLM → Gradium TTS → Twilio Out
                ↓
  Call ends → Cekura (transcript + audio) + local call store
                ↓
  POST /report → Nemotron analysis → automation report
```

## Quick Demo

```bash
# 1. Install dependencies
uv sync

# 2. Fill in credentials
cp .env.example .env
# Edit .env with Twilio, NVIDIA, Gradium, and Cekura keys

# 3. Expose local server to Twilio
ngrok http 8000

# 4. Start the server
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5. Trigger calls across different scenarios
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567", "scenario": "hours_inquiry"}'

curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"to": "+15551234567", "scenario": "refund_request"}'

# 6. Check call status
curl http://localhost:8000/calls

# 7. Generate an automation report (use call SIDs from step 6)
curl -X POST http://localhost:8000/report \
  -H "Content-Type: application/json" \
  -d '{"call_sids": ["CA...", "CA..."]}'
```

## Scenarios

| ID | Name | Description |
|----|------|-------------|
| `general_support` | General Support | Open-ended inquiry to explore the support experience |
| `hours_inquiry` | Hours Inquiry | Asks about hours, weekends, and holiday closures |
| `refund_request` | Refund Request | Mildly frustrated customer requesting a refund |
| `appointment_booking` | Appointment Booking | Customer scheduling a service appointment |
| `product_question` | Product Question | Pre-purchase questions about features and pricing |

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/call` | Initiate an outbound call — body: `{"to": "+1...", "scenario": "..."}` |
| `GET` | `/calls` | List all calls with status and metadata |
| `GET` | `/calls/{call_sid}` | Get a single call record |
| `POST` | `/report` | Generate report — body: `{"call_sids": ["CA..."]}` |

## Setup

See [SETUP.md](SETUP.md) for full setup instructions including Twilio CLI, Cekura, and ngrok configuration.

## Tech Stack

- **Pipecat** — voice agent orchestration
- **NVIDIA Nemotron** — LLM (hosted on AWS via vLLM)
- **Gradium** — text-to-speech
- **NVIDIA ASR** — speech-to-text
- **Twilio** — phone calling
- **Cekura** — call analysis and observability
- **FastAPI** — web server
