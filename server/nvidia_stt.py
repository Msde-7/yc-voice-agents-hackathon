"""NVIDIA WebSocket STT service for Pipecat."""

import asyncio
import json
import os
from typing import AsyncGenerator

import websockets
from loguru import logger
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language


class NvidiaWebSocketSTTService(STTService):
    """Streams audio to NVIDIA ASR over WebSocket and emits transcription frames."""

    def __init__(self, url: str | None = None, language: Language = Language.EN, **kwargs):
        super().__init__(**kwargs)
        self._url = url or os.environ["NVIDIA_ASR_URL"]
        self._language = language
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._receive_task: asyncio.Task | None = None

    async def start(self, frame: Frame):
        await super().start(frame)
        self._ws = await websockets.connect(self._url)
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def stop(self, frame: Frame):
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            await self._ws.close()
        await super().stop(frame)

    async def cancel(self, frame: CancelFrame):
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            await self._ws.close()
        await super().cancel(frame)

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if self._ws and not self._ws.closed:
            await self._ws.send(audio)
        yield  # yields nothing; transcripts come via _receive_loop

    async def _receive_loop(self):
        try:
            async for message in self._ws:
                await self._handle_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"NVIDIA STT receive error: {e}")
            await self.push_frame(ErrorFrame(str(e)))

    async def _handle_message(self, message: str):
        try:
            data = json.loads(message)
            text = data.get("text", "")
            is_final = data.get("is_final", False)
            if not text:
                return
            if is_final:
                await self.push_frame(TranscriptionFrame(text, "", language=self._language))
                await self.push_frame(InterimTranscriptionFrame("", "", language=self._language))
            else:
                await self.push_frame(InterimTranscriptionFrame(text, "", language=self._language))
        except Exception as e:
            logger.error(f"NVIDIA STT message parse error: {e}")
