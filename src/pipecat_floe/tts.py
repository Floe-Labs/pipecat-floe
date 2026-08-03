#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Floe text-to-speech service for Pipecat.

Floe's ``/v1/audio/speech`` endpoint is OpenAI-compatible, so this service is a
thin subclass of Pipecat's :class:`OpenAITTSService` that points the client at
Floe and reads the Floe agent key from the environment. Streaming audio
output, usage/TTFB metrics, and tracing are inherited unchanged.
"""

from __future__ import annotations

import os

import httpx
from pipecat.services.openai.tts import OpenAITTSService

from pipecat_floe.constants import FLOE_API_KEY_ENV, FLOE_BASE_URL


class FloeTTSService(OpenAITTSService):
    """Text-to-speech service that routes OpenAI-compatible speech through Floe.

    The ``model`` is a fully qualified ``provider/model`` ID (for example
    ``"openai/tts-1"``). The synthesized speech is metered on your Floe balance
    and bounded by any spend cap set on the agent key.

    Because Floe is OpenAI-compatible, the underlying
    :class:`~pipecat.services.openai.tts.OpenAITTSService` behaviour (PCM
    streaming, metrics, tracing, voice validation) works unchanged.
    """

    def __init__(
        self,
        *,
        model: str = "openai/tts-1",
        voice: str = "alloy",
        api_key: str | None = None,
        base_url: str = FLOE_BASE_URL,
        task_id: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize the Floe TTS service.

        Args:
            model: Fully qualified ``provider/model`` TTS ID. Defaults to
                ``"openai/tts-1"``.
            voice: Voice ID to synthesize with. Defaults to ``"alloy"``.
            api_key: Floe agent key. If ``None``, the value of the
                ``FLOE_API_KEY`` environment variable is used.
            base_url: Floe OpenAI-compatible base URL. Defaults to
                :data:`~pipecat_floe.constants.FLOE_BASE_URL`.
            task_id: Optional Floe task ID sent as the ``X-Floe-Task-Id`` header
                on every request, so a per-task budget can bound one
                conversation. Omit to leave the header off.
            **kwargs: Additional keyword arguments forwarded to
                :class:`~pipecat.services.openai.tts.OpenAITTSService`.

        Raises:
            ValueError: If no API key is provided and ``FLOE_API_KEY`` is unset.
        """
        resolved_key = api_key or os.environ.get(FLOE_API_KEY_ENV)
        if not resolved_key:
            raise ValueError(
                "A Floe API key is required. Pass api_key=... or set the "
                f"{FLOE_API_KEY_ENV} environment variable."
            )

        # OpenAITTSService builds its own AsyncOpenAI client and does not expose
        # a default_headers argument. To attach the optional X-Floe-Task-Id
        # header we supply an httpx client carrying it as a default header,
        # unless the caller already passed their own http_client.
        if task_id is not None and "http_client" not in kwargs:
            kwargs["http_client"] = httpx.AsyncClient(
                headers={"X-Floe-Task-Id": task_id}
            )

        # Prefer Pipecat's non-deprecated settings API for model + voice. If the
        # caller supplied their own settings, leave it untouched.
        settings = kwargs.pop("settings", None) or self.Settings(
            model=model, voice=voice
        )

        super().__init__(
            settings=settings,
            api_key=resolved_key,
            base_url=base_url,
            **kwargs,
        )
