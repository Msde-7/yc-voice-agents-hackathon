"""Gunk voice agent pipeline — simulates a customer calling a business."""

import os
import sys
from collections.abc import Callable

from cekura.pipecat import PipecatTracer
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from nemotron_llm import NemotronLLMService
from nvidia_stt import NvidiaWebSocketSTTService
from scenarios import SCENARIOS

load_dotenv()

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def run_bot(
    runner_args: RunnerArguments,
    scenario_id: str = "general_support",
    on_finished: Callable[[list], None] | None = None,
    _call_data: dict | None = None,
):
    """Build and run the Gunk Pipecat pipeline for a single call.

    Args:
        runner_args: Pipecat runner arguments (contains the WebSocket).
        scenario_id: Which customer scenario to simulate.
        on_finished: Optional callback invoked with context.messages when the pipeline ends.
        _call_data: Pre-parsed telephony call data; parsed from the WebSocket if not provided.
    """
    if _call_data is None:
        _transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    else:
        call_data = _call_data

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

    scenario = SCENARIOS[scenario_id]
    context = LLMContext(
        messages=[{"role": "system", "content": scenario["system_prompt"]}]
    )
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

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

    tracer = PipecatTracer(
        api_key=os.environ["CEKURA_API_KEY"],
        agent_id=int(os.environ["CEKURA_AGENT_ID"]),
    )

    # Two-step setup so we can pass PipelineParams (audio rates, VAD)
    # observe_and_create_task creates PipelineTask with no params, so we do it manually.
    pipeline = tracer.observe_pipeline(
        pipeline,
        context,
        runner_args=runner_args,
        session_id=call_data["call_id"],
        custom_metadata={"scenario": scenario_id},
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
            allow_interruptions=True,
        ),
    )

    tracer.register_task_handlers(task, transport=transport)

    if on_finished is not None:
        @task.event_handler("on_pipeline_finished")
        async def _on_finished(task_instance, frame):
            on_finished(list(context.messages))

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
