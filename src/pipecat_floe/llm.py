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

from floe_guard import (
    hosted_enforcement_available,
    hosted_remaining_usd,
    turn_cost,
)
from loguru import logger
from pipecat.metrics.metrics import LLMTokenUsage
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
        provider_key: str | None = None,
        cost_receipts: bool = True,
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
            provider_key: Optional upstream provider key (**BYOK**). When set, it
                is sent as the ``X-Floe-Provider-Key`` header so Floe routes the
                call on *your* vendor key (e.g. your OpenAI key) and bills only
                its service fee — while still metering the call and enforcing your
                spend caps. Omit for the keyless path, where Floe uses its own
                managed provider keys.
            cost_receipts: When ``True`` (the default), log a one-line cost
                receipt after every LLM turn — the model, this turn's estimated
                USD cost, and, when a Floe key is present, the remaining hosted
                budget. Set ``False`` to silence it.
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
        extra_headers: dict[str, str] = {}
        if task_id is not None:
            extra_headers["X-Floe-Task-Id"] = task_id
        if provider_key is not None:
            extra_headers["X-Floe-Provider-Key"] = provider_key
        if extra_headers:
            default_headers = {**(default_headers or {}), **extra_headers}

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

        self._cost_receipts = cost_receipts

    async def start_llm_usage_metrics(self, tokens: LLMTokenUsage) -> None:
        """Log a per-turn cost receipt, then defer to the inherited metrics.

        Pipecat calls this once per completion with *this* turn's (non-cumulative)
        token usage. The cost figure is priced locally by ``floe-guard`` (free,
        offline, no key). The remaining-budget half is a hosted read that needs a
        Floe key — it is best-effort and fail-closed: any failure logs a debug
        line and the receipt still shows the cost. If the model cannot be priced,
        ``turn_cost`` returns ``None`` and no receipt is emitted (never a
        fabricated ``$0``).
        """
        await super().start_llm_usage_metrics(tokens)
        if not self._cost_receipts:
            return

        remaining = None
        if hosted_enforcement_available():
            try:
                remaining = hosted_remaining_usd()
            except Exception:
                logger.debug("floe: budget read failed; showing cost without budget")

        cost = turn_cost(
            self._settings.model,
            tokens.prompt_tokens,
            tokens.completion_tokens,
            remaining_usd=remaining,
        )
        if cost is None:
            return
        logger.info(cost.format())
