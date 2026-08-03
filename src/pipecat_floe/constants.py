#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Shared defaults for the Floe Pipecat services."""

# OpenAI-compatible REST base URL for the LLM and TTS legs. Floe exposes
# /v1/chat/completions and /v1/audio/speech at this base, so both are plain
# base-URL swaps over Pipecat's OpenAI services.
FLOE_BASE_URL = "https://credit-api.floelabs.xyz/v1"

# WebSocket URL for the streaming-STT leg. Unlike the LLM/TTS legs this is a
# net-new streaming protocol (raw PCM up, JSON transcripts down), not a
# base-URL swap of an OpenAI endpoint.
FLOE_STT_WS_URL = "wss://credit-api.floelabs.xyz/v1/audio/transcriptions/stream"

# Environment variable read for the Floe agent key when one is not passed
# explicitly to a service constructor.
FLOE_API_KEY_ENV = "FLOE_API_KEY"
