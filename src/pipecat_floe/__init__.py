#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Floe services for Pipecat.

One Floe key powers the LLM, STT, and TTS legs of a Pipecat voice pipeline —
metered per call with pre-call spend caps. The LLM and TTS legs are
OpenAI-compatible base-URL swaps; the STT leg is a dedicated streaming plugin
that talks Floe's transcription WebSocket protocol.

Exports:
    FloeLLMService: OpenAI-compatible LLM routed through Floe.
    FloeTTSService: OpenAI-compatible text-to-speech routed through Floe.
    FloeSTTService: Streaming speech-to-text over Floe's WebSocket.
    FLOE_BASE_URL: Default Floe OpenAI-compatible base URL.
    FLOE_STT_WS_URL: Default Floe streaming-STT WebSocket URL.
"""

from pipecat_floe.constants import FLOE_BASE_URL, FLOE_STT_WS_URL
from pipecat_floe.llm import FloeLLMService
from pipecat_floe.stt import FloeSTTService
from pipecat_floe.tts import FloeTTSService

__version__ = "0.1.0"

__all__ = [
    "FloeLLMService",
    "FloeTTSService",
    "FloeSTTService",
    "FLOE_BASE_URL",
    "FLOE_STT_WS_URL",
    "__version__",
]
