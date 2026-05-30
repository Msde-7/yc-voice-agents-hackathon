"""Gunk local test bot — browser-based testing via WebRTC (no Twilio needed).

Run with:
    uv run bot_local.py

Then open http://localhost:7860 in your browser and click Connect.
The bot will speak first as a customer calling your "business".
"""

import os

from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.gradium.stt import GradiumSTTService
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from nemotron_llm import NemotronLLMService
from scenarios import SCENARIOS

load_dotenv(override=True)

# Change this to test different scenarios
SCENARIO_ID = "hours_inquiry"


async def run_bot(transport: BaseTransport):
    scenario = SCENARIOS[SCENARIO_ID]

    stt = GradiumSTTService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumSTTService.Settings(language="en"),
    )

    llm = NemotronLLMService()

    tts = GradiumTTSService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumTTSService.Settings(
            voice=os.getenv("GRADIUM_VOICE_ID", "Eu9iL_CYe8N-Gkx_"),
        ),
    )

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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            allow_interruptions=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message({
            "role": "user",
            "content": "(The call just connected. Start the conversation as the customer.)",
        })
        await worker.queue_frames([LLMRunFrame()])

    runner = WorkerRunner()
    await runner.run(worker)


async def bot(runner_args: RunnerArguments):
    transport = SmallWebRTCTransport(
        webrtc_connection=runner_args.webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
