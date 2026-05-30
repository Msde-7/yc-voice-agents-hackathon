"""Gunk voice agent pipeline — simulates a customer calling a business."""

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.runner.types import RunnerArguments, WebSocketRunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from nemotron_llm import NemotronLLMService
from nvidia_stt import NvidiaWebSocketSTTService

load_dotenv()

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

SYSTEM_PROMPT = """You are a customer calling a business to test their support experience.
Your goal is to have a natural, realistic conversation to understand how the business handles common customer requests.
Start with a simple inquiry (like asking about hours, services, or pricing), then follow where the conversation leads.
Be polite, natural, and realistic — behave like a real customer would.
Keep your responses short and conversational since this is a phone call.
When you feel you have learned enough about the business's support process, politely end the call."""


async def run_bot(runner_args: RunnerArguments):
    """Build and run the Gunk Pipecat pipeline for a single call."""
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
        auth_token=os.environ["TWILIO_AUTH_TOKEN"],
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    stt = NvidiaWebSocketSTTService()

    llm = NemotronLLMService()

    tts = GradiumTTSService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumTTSService.Settings(
            voice=os.getenv("GRADIUM_VOICE_ID", "Eu9iL_CYe8N-Gkx_"),
        ),
    )

    context = OpenAILLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}]
    )
    context_aggregator = llm.create_context_aggregator(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
            allow_interruptions=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    @transport.event_handler("on_client_disconnected")
    async def on_disconnect(transport, client):
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
