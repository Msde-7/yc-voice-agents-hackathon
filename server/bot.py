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
    """Drops audio input while the bot is speaking to block Twilio echo from reaching STT."""

    def __init__(self):
        super().__init__()
        self._muted = False

    def mute(self) -> None:
        self._muted = True

    def unmute(self) -> None:
        self._muted = False

    async def process_frame(self, frame: object, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._muted and isinstance(frame, AudioRawFrame):
            return  # drop echo audio; super() already handled lifecycle
        await self.push_frame(frame, direction)


class TTSActivityTracker(FrameProcessor):
    """Mutes the STTGate when TTS audio is flowing out, unmutes after playback ends.

    Placed after GradiumTTSService in the pipeline so it sees actual output audio
    frames — more reliable than transport events which may not be registered.
    """

    def __init__(self, gate: STTGate, post_speech_delay: float = 2.0):
        super().__init__()
        self._gate = gate
        self._post_speech_delay = post_speech_delay
        self._unmute_task: asyncio.Task | None = None

    async def process_frame(self, frame: object, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, AudioRawFrame):
            self._gate.mute()
            # Reset the unmute countdown every time an audio frame arrives
            if self._unmute_task and not self._unmute_task.done():
                self._unmute_task.cancel()
            self._unmute_task = asyncio.create_task(self._delayed_unmute())
        await self.push_frame(frame, direction)

    async def _delayed_unmute(self) -> None:
        await asyncio.sleep(self._post_speech_delay)
        self._gate.unmute()


async def run_bot(
    runner_args: RunnerArguments,
    scenario_id: str = "general_support",
    scenario_data: Scenario | None = None,
    on_finished: Callable[[list], None] | None = None,
    _call_data: dict | None = None,
):
    """Build and run the Gunk Pipecat pipeline for a single call."""
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
    tts_tracker = TTSActivityTracker(gate=stt_gate, post_speech_delay=2.0)
    llm = NemotronLLMService()

    _end_call_tools = ToolsSchema(standard_tools=[
        FunctionSchema(
            name="end_call",
            description="End the phone call. Call this only after a natural conversation with several follow-ups.",
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

    context = LLMContext(
        messages=[{"role": "system", "content": scenario["system_prompt"]}],
    )
    _assistant_turns = 0
    _MIN_TURNS_BEFORE_HANGUP = 3
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
            tts_tracker,   # mutes STTGate when audio is actually flowing out
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    tracer = PipecatTracer(
        api_key=os.environ["CEKURA_API_KEY"],
        agent_id=int(os.environ["CEKURA_AGENT_ID"]),
    )

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

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        context.add_message({"role": "user", "content": "(The call just connected. Start the conversation as the customer.)"})
        await task.queue_frames([LLMRunFrame()])

    @context_aggregator.assistant().event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn(aggregator, message):
        nonlocal _assistant_turns
        _assistant_turns += 1
        if _assistant_turns == _MIN_TURNS_BEFORE_HANGUP:
            await task.queue_frames([LLMSetToolsFrame(tools=_end_call_tools)])

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
        _call_on_finished()
        await task.queue_frames([EndFrame()])

    @task.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(task_instance, frame):
        _call_on_finished()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
