"""Gunk FastAPI server — handles Twilio webhooks and WebSocket audio streams."""

import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse
from loguru import logger
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

import analysis_store
import call_store
from bot import run_bot
from business_context import get_business_context
from pipecat.runner.types import WebSocketRunnerArguments
from report import generate_report
from scenario_generator import generate_scenarios
from scenarios import SCENARIOS, Scenario

load_dotenv()

app = FastAPI(title="Gunk")

_twilio = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

# Maps call_sid → scenario_id
_pending_scenarios: dict[str, str] = {}
# Maps call_sid → full Scenario dict (for dynamically generated scenarios)
_pending_scenario_data: dict[str, Scenario] = {}
# Signals waiting analysis workers that a call has completed
_call_complete_events: dict[str, asyncio.Event] = {}


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


def _make_twiml_url(request: Request) -> str:
    host = request.headers.get("host", "localhost")
    scheme = "https" if request.url.scheme == "https" else "http"
    return f"{scheme}://{host}/twiml"


def _dial(to_number: str, scenario_id: str, twiml_url: str, scenario_data: Scenario | None = None) -> str:
    """Initiate an outbound Twilio call. Returns call_sid."""
    from_number = os.environ["TWILIO_PHONE_NUMBER"]
    call = _twilio.calls.create(to=to_number, from_=from_number, url=twiml_url, method="POST")
    _pending_scenarios[call.sid] = scenario_id
    if scenario_data:
        _pending_scenario_data[call.sid] = scenario_data
    call_store.create(call.sid, to_number, scenario_id)
    logger.info(f"Initiated call {call.sid} to {to_number} (scenario={scenario_id})")
    return call.sid


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
    logger.info(f"Returning TwiML for {to_number} → {ws_url}")
    return HTMLResponse(content=twiml, media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Twilio Media Stream WebSocket — runs the Pipecat pipeline."""
    await websocket.accept()
    from pipecat.runner.utils import parse_telephony_websocket
    _transport_type, call_data = await parse_telephony_websocket(websocket)
    call_sid = call_data.get("call_id", "")

    scenario_id = _pending_scenarios.pop(call_sid, "general_support")
    scenario_data = _pending_scenario_data.pop(call_sid, None)
    call_store.update_status(call_sid, "in_progress")

    def on_finished(messages: list) -> None:
        call_store.update_status(
            call_sid,
            "completed",
            ended_at=datetime.now(timezone.utc),
            transcript=messages,
        )
        event = _call_complete_events.pop(call_sid, None)
        if event:
            event.set()

    await run_bot(
        WebSocketRunnerArguments(websocket=websocket),
        scenario_id=scenario_id,
        scenario_data=scenario_data,
        on_finished=on_finished,
        _call_data=call_data,
    )


async def _run_analysis(
    analysis_id: str,
    to_number: str,
    requested_scenarios: list[str] | None,
    twiml_url: str,
    website: str | None,
):
    """Background task: scrape business, generate scenarios, run calls, produce report."""
    call_sids = []

    # Step 1: discover business context via Firecrawl
    logger.info(f"Analysis {analysis_id}: fetching business context for {to_number}")
    try:
        context = await get_business_context(to_number, website=website)
        analysis_store.update(analysis_id, business_context=context or None)
    except Exception as e:
        logger.error(f"Business context lookup failed: {e}")
        context = ""

    # Step 2: generate tailored scenarios (or use requested static ones)
    if requested_scenarios:
        # User specified scenarios by name — use static definitions
        scenario_map = {sid: SCENARIOS[sid] for sid in requested_scenarios if sid in SCENARIOS}
    else:
        # Generate tailored scenarios from business context
        count = 5
        scenario_map = await generate_scenarios(context, count=count)

    scenario_items = list(scenario_map.items())
    analysis_store.update(analysis_id, scenarios=[sid for sid, _ in scenario_items])
    logger.info(f"Analysis {analysis_id}: running {len(scenario_items)} scenarios")

    for scenario_id, scenario_data in scenario_items:
        try:
            call_sid = _dial(to_number, scenario_id, twiml_url, scenario_data=scenario_data)
            call_sids.append(call_sid)

            # Wait for this call to complete before dialling the next one
            event = asyncio.Event()
            _call_complete_events[call_sid] = event
            try:
                await asyncio.wait_for(event.wait(), timeout=300)  # 5 min max per call
            except asyncio.TimeoutError:
                logger.warning(f"Call {call_sid} timed out waiting to complete")
                _call_complete_events.pop(call_sid, None)

            analysis_store.update(analysis_id, call_sids=list(call_sids))

            # Brief pause between calls so the business doesn't get back-to-back rings
            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Analysis {analysis_id}: scenario {scenario_id} failed: {e}")

    # Generate the combined report from all completed calls with transcripts
    records = [r for r in (call_store.get(sid) for sid in call_sids) if r and r.transcript]

    if not records:
        analysis_store.update(
            analysis_id,
            status="failed",
            error="No calls completed with transcripts",
            completed_at=datetime.now(timezone.utc),
        )
        return

    try:
        report = await generate_report(records)
        analysis_store.update(
            analysis_id,
            status="completed",
            report=report,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info(f"Analysis {analysis_id} complete — automation score: {report.automation_score}")
    except Exception as e:
        analysis_store.update(
            analysis_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc),
        )


@app.post("/analyze")
async def start_analysis(request: Request, background_tasks: BackgroundTasks):
    """Scrape the business, generate tailored scenarios, run calls, return a combined report.

    Body JSON:
      { "to": "+15551234567" }
        — scrape business by phone number, auto-generate 5 tailored scenarios

      { "to": "+15551234567", "website": "https://acmehotel.com" }
        — scrape the given website directly (skips the search step)

      { "to": "+15551234567", "scenarios": ["hours_inquiry", "refund_request"] }
        — skip generation, use these specific static scenarios instead

    Returns immediately with an analysis ID.
    Poll GET /analyze/{id} for status and the final report.
    """
    body = await request.json()
    to_number = body.get("to")
    if not to_number:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    website = body.get("website")

    # If caller passes explicit scenario names, validate and use static ones
    requested = body.get("scenarios")
    if requested:
        invalid = [s for s in requested if s not in SCENARIOS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown scenarios: {invalid}. Valid: {list(SCENARIOS)}")

    record = analysis_store.create(
        to_number,
        scenarios=requested or [],  # will be filled in after generation
        website=website,
    )
    twiml_url = _make_twiml_url(request)

    background_tasks.add_task(_run_analysis, record.id, to_number, requested, twiml_url, website)

    logger.info(f"Started analysis {record.id} for {to_number}")
    return record.model_dump(mode="json")


@app.get("/analyze/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Poll analysis status. Returns the full report when status == 'completed'."""
    record = analysis_store.get(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    return record.model_dump(mode="json")


@app.get("/analyze")
async def list_analyses():
    """List all analysis sessions."""
    return [r.model_dump(mode="json") for r in analysis_store.list_all()]


@app.post("/call")
async def initiate_call(request: Request):
    """Trigger a single outbound call (one scenario).

    Body JSON: { "to": "+15551234567", "scenario": "hours_inquiry" }
    """
    body = await request.json()
    to_number = body.get("to")
    if not to_number:
        raise HTTPException(status_code=400, detail="Missing 'to' field")

    scenario_id = body.get("scenario", "general_support")
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{scenario_id}'. Valid: {list(SCENARIOS)}")

    twiml_url = _make_twiml_url(request)
    call_sid = _dial(to_number, scenario_id, twiml_url)
    return call_store.get(call_sid).model_dump(mode="json")


@app.get("/calls")
async def list_calls():
    """List all calls. Filter by business with ?to=+1..."""
    return [r.model_dump(mode="json") for r in call_store.list_all()]


@app.get("/calls/{call_sid}")
async def get_call(call_sid: str):
    """Get a single call record."""
    record = call_store.get(call_sid)
    if not record:
        raise HTTPException(status_code=404, detail=f"Call {call_sid} not found")
    return record.model_dump(mode="json")


@app.post("/report")
async def create_report(request: Request):
    """Generate a report from completed calls.

    Body JSON: { "to": "+1..." }  — all completed calls for that number
           OR: { "call_sids": ["CA..."] }  — specific calls
    """
    body = await request.json()

    if "to" in body:
        records = [r for r in call_store.list_by_number(body["to"]) if r.transcript]
        if not records:
            raise HTTPException(status_code=400, detail=f"No completed calls found for {body['to']}")
    elif "call_sids" in body:
        records = []
        for sid in body["call_sids"]:
            r = call_store.get(sid)
            if not r:
                raise HTTPException(status_code=404, detail=f"Call {sid} not found")
            if not r.transcript:
                raise HTTPException(status_code=400, detail=f"Call {sid} has no transcript")
            records.append(r)
    else:
        raise HTTPException(status_code=400, detail="Provide either 'to' or 'call_sids'")

    report = await generate_report(records)
    return report.model_dump(mode="json")
