#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Floe LLM service for Pipecat.

Floe's ``/v1/chat/completions`` endpoint is OpenAI-compatible, so this service
is a thin subclass of Pipecat's :class:`OpenAILLMService` that points the
client at Floe and reads the Floe agent key from the environment. All metrics,
tracing, and context-aggregation behaviour is inherited unchanged from the
OpenAI service.
"""

from __future__ import annotations

import os

from pipecat.services.openai.llm import OpenAILLMService

from pipecat_floe.constants import FLOE_API_KEY_ENV, FLOE_BASE_URL


class FloeLLMService(OpenAILLMService):
    """LLM service that routes OpenAI-compatible chat completions through Floe.

    Model IDs are fully qualified ``provider/model`` strings (for example
    ``"openai/gpt-4o-mini"`` or ``"anthropic/claude-sonnet-4-6"``) — that is
    what Floe's inference gateway expects. The call is metered on your Floe
    balance and bounded by any spend cap set on the agent key.

    Because Floe is OpenAI-compatible, every capability of the underlying
    :class:`~pipecat.services.openai.llm.OpenAILLMService` (streaming, tool
    calls, usage/TTFB metrics, OpenTelemetry tracing) works unchanged.
    """

    def __init__(
        self,
        *,
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = FLOE_BASE_URL,
        task_id: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize the Floe LLM service.

        Args:
            model: Fully qualified ``provider/model`` ID to run (for example
                ``"openai/gpt-4o-mini"``). Defaults to ``"openai/gpt-4o-mini"``.
            api_key: Floe agent key. If ``None``, the value of the
                ``FLOE_API_KEY`` environment variable is used.
            base_url: Floe OpenAI-compatible base URL. Defaults to
                :data:`~pipecat_floe.constants.FLOE_BASE_URL`.
            task_id: Optional Floe task ID sent as the ``X-Floe-Task-Id`` header
                on every request, so a per-task budget can bound one
                conversation. Omit to leave the header off.
            **kwargs: Additional keyword arguments forwarded to
                :class:`~pipecat.services.openai.llm.OpenAILLMService`.

        Raises:
            ValueError: If no API key is provided and ``FLOE_API_KEY`` is unset.
        """
        resolved_key = api_key or os.environ.get(FLOE_API_KEY_ENV)
        if not resolved_key:
            raise ValueError(
                "A Floe API key is required. Pass api_key=... or set the "
                f"{FLOE_API_KEY_ENV} environment variable."
            )

        default_headers = kwargs.pop("default_headers", None)
        if task_id is not None:
            default_headers = {**(default_headers or {}), "X-Floe-Task-Id": task_id}

        # Prefer Pipecat's non-deprecated settings API for the model. If the
        # caller supplied their own settings, leave it untouched.
        settings = kwargs.pop("settings", None) or self.Settings(model=model)

        super().__init__(
            settings=settings,
            api_key=resolved_key,
            base_url=base_url,
            default_headers=default_headers,
            **kwargs,
        )
