#
# Copyright (c) 2026, Floe Labs
#
# SPDX-License-Identifier: MIT
#

"""Per-turn cost receipt tests for :class:`FloeLLMService`.

These exercise the ``start_llm_usage_metrics`` override in isolation: no network,
no real Floe key. Construction of the base OpenAI service is offline; the hosted
budget read is patched so nothing ever leaves the process.
"""

from __future__ import annotations

import asyncio

import pytest
from loguru import logger
from pipecat.metrics.metrics import LLMTokenUsage

from pipecat_floe import FloeLLMService

TOKENS = LLMTokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)


def _unavailable(*_args, **_kwargs) -> float:
    """Stand-in for a hosted budget read that can't reach Floe (fail-closed)."""
    raise RuntimeError("hosted unavailable")


@pytest.fixture
def sink() -> list[str]:
    """Capture loguru INFO+ messages emitted during a test."""
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(m.record["message"]), level="DEBUG")
    try:
        yield messages
    finally:
        logger.remove(sink_id)


def _service(**kwargs) -> FloeLLMService:
    return FloeLLMService(model="openai/gpt-4o", api_key="floe_test", **kwargs)


def test_receipt_logged_on_by_default(sink, monkeypatch):
    # On by default: a priceable turn logs a receipt. The hosted read is patched
    # to fail, so the line is cost-only (fail-closed) and no network is hit.
    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", _unavailable)
    svc = _service()

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    receipts = [m for m in sink if m.startswith("floe · ")]
    # Display uses the short model id (gpt-4o), though pricing uses the full id.
    assert receipts == ["floe · gpt-4o · $0.0075 est"]


def test_cost_receipts_false_suppresses(sink):
    # cost_receipts=False returns before any hosted read — no patch needed.
    svc = _service(cost_receipts=False)

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    assert not [m for m in sink if m.startswith("floe · ")]


def test_budget_half_appended_when_key_present(sink, monkeypatch):
    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", lambda *a, **k: 12.34)
    svc = _service()

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == ["floe · gpt-4o · $0.0075 est · left $12.34"]


def test_budget_read_failure_drops_budget_and_is_throttled(sink, monkeypatch):
    calls: list[bool] = []

    def boom(*_a, **_k) -> float:
        calls.append(True)
        raise RuntimeError("hosted down")

    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", boom)
    svc = _service()

    async def two_turns() -> None:
        # Two turns inside the TTL window.
        await svc.start_llm_usage_metrics(TOKENS)
        await svc.start_llm_usage_metrics(TOKENS)

    # Must not raise into the pipeline; the budget is dropped (no `left $…`) and
    # the receipt still shows the cost on every turn.
    asyncio.run(two_turns())

    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == [
        "floe · gpt-4o · $0.0075 est",
        "floe · gpt-4o · $0.0075 est",
    ]
    # Throttled by the TTL: the failing endpoint is hit at most once per window.
    assert calls == [True]


def test_unpriceable_model_skips_hosted_read(sink, monkeypatch):
    # Price FIRST: an unpriceable model must short-circuit before any hosted
    # network call — even when a key is present.
    calls: list[bool] = []

    def spy(*_a, **_k) -> float:
        calls.append(True)
        return 12.34

    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", spy)
    monkeypatch.setattr("pipecat_floe.llm.turn_cost", lambda *a, **k: None)
    svc = _service()

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    assert calls == []  # hosted endpoint never touched
    assert not [m for m in sink if m.startswith("floe · ")]


def test_budget_read_uses_in_code_key_not_env(sink, monkeypatch):
    # Devin's bug: with an in-code api_key and no FLOE_API_KEY in env, the
    # balance must be read for the in-code key — not the env key (absent here).
    monkeypatch.delenv("FLOE_API_KEY", raising=False)
    seen: list[str | None] = []

    def spy(api_key=None, *_a, **_k) -> float:
        seen.append(api_key)
        return 42.0

    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", spy)
    svc = FloeLLMService(
        model="openai/gpt-4o", api_key="floe_incode", cost_receipts=True
    )

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    # The service's own configured key reached the hosted read, not None/env.
    assert seen == ["floe_incode"]
    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == ["floe · gpt-4o · $0.0075 est · left $42.00"]
