#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Minimal Pipecat voice bot with all three legs on Floe.

One ``FLOE_API_KEY`` powers the streaming STT, the LLM, and the TTS legs — one
key, one ledger, one budget. The transport is Pipecat's built-in WebSocket
server, so the bot runs locally with no cloud transport account.

Run:
    pip install pipecat-floe[example]  # or: pip install -r requirements.txt
    cp .env.example .env               # fill in FLOE_API_KEY
    python bot.py

Then connect an audio WebSocket client to ws://localhost:8765 (for example the
Pipecat client SDKs or the websocket examples in the Pipecat repo).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.transports.websocket.server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

from pipecat_floe import FloeLLMService, FloeSTTService, FloeTTSService

load_dotenv()


async def main() -> None:
    """Build and run the three-leg Floe voice pipeline."""
    if not os.environ.get("FLOE_API_KEY"):
        raise SystemExit("Set FLOE_API_KEY in your environment (see .env.example).")

    # Local WebSocket transport: audio in/out, server-side VAD for turn-taking.
    transport = WebsocketServerTransport(
        params=WebsocketServerParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
        ),
        host="localhost",
        port=8765,
    )

    # All three legs on one Floe key. Each service reads FLOE_API_KEY from the
    # environment; a single spend cap on that agent bounds the whole run.
    stt = FloeSTTService(model="deepgram/nova-3")
    llm = FloeLLMService(model="openai/gpt-4o-mini")
    tts = FloeTTSService(model="openai/tts-1", voice="alloy")

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful voice assistant. Keep replies short and "
                    "conversational — your text is spoken aloud."
                ),
            }
        ]
    )
    aggregators = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    task = PipelineTask(pipeline)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):  # noqa: ANN001
        logger.info("Client connected — say hello.")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):  # noqa: ANN001
        logger.info("Client disconnected.")
        await task.cancel()

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
