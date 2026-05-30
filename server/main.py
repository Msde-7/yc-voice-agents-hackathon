"""Gunk FastAPI server — handles Twilio webhooks and WebSocket audio streams."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from loguru import logger
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from bot import run_bot
from pipecat.runner.types import WebSocketRunnerArguments

load_dotenv()

app = FastAPI(title="Gunk")

_twilio = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


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
    await run_bot(runner_args)


@app.post("/call")
async def initiate_call(request: Request):
    """Trigger an outbound call to a target business number.

    Body JSON: { "to": "+15551234567" }
    """
    body = await request.json()
    to_number = body.get("to")
    if not to_number:
        return {"error": "Missing 'to' field"}

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
    logger.info(f"Initiated call {call.sid} to {to_number}")
    return {"call_sid": call.sid, "status": call.status}
