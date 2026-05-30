"""Gunk FastAPI server — handles Twilio webhooks and WebSocket audio streams."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse
from loguru import logger
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

import call_store
from bot import run_bot
from pipecat.runner.types import WebSocketRunnerArguments
from report import generate_report
from scenarios import SCENARIOS

load_dotenv()

app = FastAPI(title="Gunk")

_twilio = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

# Maps call_sid → scenario_id so the /ws handler knows which scenario to run
_pending_scenarios: dict[str, str] = {}
# Maps call_sid → to_number for record creation in /ws
_pending_numbers: dict[str, str] = {}


def _twiml_response(websocket_url: str, to_number: str, from_number: str) -> str:
    """Build TwiML that streams call audio to our WebSocket endpoint."""
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=websocket_url)
    stream.parameter(name="to_number", value=to_number)
    stream.parameter(name="from_number", value=from_number)
    connect.append(stream)
    response.append(connect)
    response.pause(length=40)
    return str(response)


@app.post("/twiml")
async def twiml_webhook(request: Request) -> HTMLResponse:
    """Called by Twilio when an outbound call connects — returns streaming TwiML."""
    form = await request.form()
    to_number = form.get("To", "")
    from_number = form.get("From", "")

    host = request.headers.get("host", "localhost")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/ws"

    twiml = _twiml_response(ws_url, to_number, from_number)
    logger.info(f"Returning TwiML for call {to_number} → {ws_url}")
    return HTMLResponse(content=twiml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Twilio Media Stream WebSocket — runs the Pipecat pipeline."""
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    runner_args = WebSocketRunnerArguments(websocket=websocket)

    # Peek at call_id before handing off to run_bot, so we can update the store.
    # parse_telephony_websocket is called inside run_bot; we pass the IDs via closure.
    # Instead, we extract scenario/number from pending dicts inside run_bot via callback.
    # For simplicity, pass scenario_id and on_finished through a pre-identified call_sid.
    # Twilio sends the call_sid in the first "connected" message; we intercept it here.

    from pipecat.runner.utils import parse_telephony_websocket
    _transport_type, call_data = await parse_telephony_websocket(websocket)
    call_sid = call_data.get("call_id", "")

    scenario_id = _pending_scenarios.pop(call_sid, "general_support")
    to_number = _pending_numbers.pop(call_sid, "")

    call_store.update_status(call_sid, "in_progress")

    def on_finished(messages: list) -> None:
        call_store.update_status(
            call_sid,
            "completed",
            ended_at=datetime.now(timezone.utc),
            transcript=messages,
        )

    await run_bot(
        runner_args,
        scenario_id=scenario_id,
        on_finished=on_finished,
        _call_data=call_data,
    )


@app.post("/call")
async def initiate_call(request: Request):
    """Trigger an outbound call to a target business number.

    Body JSON: { "to": "+15551234567", "scenario": "hours_inquiry" }
    Available scenarios: general_support, hours_inquiry, refund_request,
                         appointment_booking, product_question
    """
    body = await request.json()
    to_number = body.get("to")
    if not to_number:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    scenario_id = body.get("scenario", "general_support")
    if scenario_id not in SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{scenario_id}'. Valid: {list(SCENARIOS)}",
        )

    from_number = os.environ["TWILIO_PHONE_NUMBER"]
    host = request.headers.get("host", "localhost")
    scheme = "https" if request.url.scheme == "https" else "http"
    twiml_url = f"{scheme}://{host}/twiml"

    call = _twilio.calls.create(
        to=to_number,
        from_=from_number,
        url=twiml_url,
        method="POST",
    )

    _pending_scenarios[call.sid] = scenario_id
    _pending_numbers[call.sid] = to_number
    record = call_store.create(call.sid, to_number, scenario_id)

    logger.info(f"Initiated call {call.sid} to {to_number} (scenario={scenario_id})")
    return record.model_dump(mode="json")


@app.get("/calls")
async def list_calls():
    """List all calls with their status and metadata."""
    return [r.model_dump(mode="json") for r in call_store.list_all()]


@app.get("/calls/{call_sid}")
async def get_call(call_sid: str):
    """Get a single call record by SID."""
    record = call_store.get(call_sid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Call {call_sid} not found")
    return record.model_dump(mode="json")


@app.post("/report")
async def create_report(request: Request):
    """Generate an automation analysis report from completed calls.

    Body JSON: { "call_sids": ["CA...", "CA..."] }
    Returns a structured report identifying which parts of the support flow
    could be automated vs. which need human agents.
    """
    body = await request.json()
    call_sids = body.get("call_sids", [])
    if not call_sids:
        raise HTTPException(status_code=400, detail="Missing 'call_sids' field")

    records = []
    for sid in call_sids:
        record = call_store.get(sid)
        if not record:
            raise HTTPException(status_code=404, detail=f"Call {sid} not found")
        if not record.transcript:
            raise HTTPException(
                status_code=400,
                detail=f"Call {sid} has no transcript (status: {record.status})",
            )
        records.append(record)

    report = await generate_report(records)
    return report.model_dump(mode="json")
