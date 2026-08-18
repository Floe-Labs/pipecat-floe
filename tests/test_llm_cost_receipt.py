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
    # No key present → local cost only, no budget half, no network.
    monkeypatch.setattr("pipecat_floe.llm.hosted_enforcement_available", lambda: False)
    svc = _service()

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == ["floe · openai/gpt-4o · $0.0075 est"]


def test_cost_receipts_false_suppresses(sink, monkeypatch):
    monkeypatch.setattr("pipecat_floe.llm.hosted_enforcement_available", lambda: False)
    svc = _service(cost_receipts=False)

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    assert not [m for m in sink if m.startswith("floe · ")]


def test_budget_half_appended_when_key_present(sink, monkeypatch):
    monkeypatch.setattr("pipecat_floe.llm.hosted_enforcement_available", lambda: True)
    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", lambda: 12.34)
    svc = _service()

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == ["floe · openai/gpt-4o · $0.0075 est · left $12.34"]


def test_budget_read_failure_is_fail_closed(sink, monkeypatch):
    def boom() -> float:
        raise RuntimeError("hosted down")

    monkeypatch.setattr("pipecat_floe.llm.hosted_enforcement_available", lambda: True)
    monkeypatch.setattr("pipecat_floe.llm.hosted_remaining_usd", boom)
    svc = _service()

    # Must not raise into the pipeline; still shows cost without the budget half.
    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    receipts = [m for m in sink if m.startswith("floe · ")]
    assert receipts == ["floe · openai/gpt-4o · $0.0075 est"]


def test_unpriceable_model_emits_no_receipt(sink, monkeypatch):
    monkeypatch.setattr("pipecat_floe.llm.hosted_enforcement_available", lambda: False)
    svc = _service()
    # Simulate a model the cost map can't price → turn_cost returns None.
    monkeypatch.setattr("pipecat_floe.llm.turn_cost", lambda *a, **k: None)

    asyncio.run(svc.start_llm_usage_metrics(TOKENS))

    assert not [m for m in sink if m.startswith("floe · ")]
