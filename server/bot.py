"""Gunk voice agent pipeline — simulates a customer calling a business."""

import asyncio
import os
import sys
from collections.abc import Callable

from cekura.pipecat import PipecatTracer
from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import AudioRawFrame, EndFrame, LLMRunFrame, LLMSetToolsFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from nemotron_llm import NemotronLLMService
from scenarios import SCENARIOS, Scenario

load_dotenv()

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


class STTGate(FrameProcessor):
    """Drops AudioRawFrames while the bot is speaking to prevent Twilio echo from reaching STT."""

    def __init__(self):
        super().__init__()
        self._bot_speaking = False

    def set_speaking(self, speaking: bool) -> None:
        self._bot_speaking = speaking

    async def process_frame(self, frame: object, direction: FrameDirection) -> None:
        if self._bot_speaking and isinstance(frame, AudioRawFrame):
            return  # swallow echo audio while bot is outputting; let base handle everything else
        await super().process_frame(frame, direction)


async def run_bot(
    runner_args: RunnerArguments,
    scenario_id: str = "general_support",
    scenario_data: Scenario | None = None,
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

    stt = GradiumSTTService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumSTTService.Settings(language="en"),
    )
    stt_gate = STTGate()
    llm = NemotronLLMService()

    _end_call_tools = ToolsSchema(standard_tools=[
        FunctionSchema(
            name="end_call",
            description="End the phone call. Call this only after a natural conversation where you have asked your question and several follow-ups.",
            properties={},
            required=[],
        )
    ])

    async def end_call(params: FunctionCallParams):
        await params.result_callback("Ending call now.")
        await params.pipeline_worker.queue_frames([EndFrame()])

    llm.register_function("end_call", end_call)

    tts = GradiumTTSService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumTTSService.Settings(
            voice=os.getenv("GRADIUM_VOICE_ID", "Eu9iL_CYe8N-Gkx_"),
        ),
    )

    scenario = scenario_data if scenario_data is not None else SCENARIOS.get(scenario_id, SCENARIOS["general_support"])

    # Start with NO tools — prevents Nemotron calling end_call on turn 1.
    # We inject end_call after the first assistant response.
    context = LLMContext(
        messages=[{"role": "system", "content": scenario["system_prompt"]}],
    )
    _assistant_turns = 0
    _MIN_TURNS_BEFORE_HANGUP = 3  # bot must speak at least 3 times before end_call is available
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt_gate,
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
            allow_interruptions=False,
        ),
    )

    tracer.register_task_handlers(task, transport=transport)

    # Prime the context and schedule the opening LLM trigger.
    # We avoid on_client_connected because FastAPIWebsocketTransport fires it
    # during setup (before our handler is registered), causing it to be missed.
    context.add_message({"role": "user", "content": "(The call just connected. Start the conversation as the customer.)"})

    async def _trigger_opening():
        await asyncio.sleep(0.5)
        await task.queue_frames([LLMRunFrame()])

    asyncio.create_task(_trigger_opening())

    @context_aggregator.assistant().event_handler("on_assistant_turn_started")
    async def on_assistant_speaking(aggregator):
        # Mute STT while bot is generating/speaking to block Twilio echo
        stt_gate.set_speaking(True)

    @context_aggregator.assistant().event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn(aggregator, message):
        nonlocal _assistant_turns
        _assistant_turns += 1
        if _assistant_turns == _MIN_TURNS_BEFORE_HANGUP:
            await task.queue_frames([LLMSetToolsFrame(tools=_end_call_tools)])
        # Brief delay before unmuting — gives TTS time to finish playing
        await asyncio.sleep(1.5)
        stt_gate.set_speaking(False)

    _finished = False

    def _call_on_finished():
        nonlocal _finished
        if _finished:
            return
        _finished = True
        if on_finished is not None:
            on_finished(list(context.messages))

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        # User hung up — save transcript and end the pipeline.
        _call_on_finished()
        await task.queue_frames([EndFrame()])

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(task_instance, frame):
        # Pipeline ended (e.g. via end_call tool) — save transcript.
        _call_on_finished()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
