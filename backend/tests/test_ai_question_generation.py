"""Regression coverage for a real production bug: SarvamAIProvider.chat()
always requested a fixed max_tokens=2048 regardless of how much output was
actually being asked for. generate_mixed_questions asks for up to 50
questions (AI Weekly Exam) or 18 (elimination battles) in one JSON
response — comfortably more than 2048 tokens' worth — so Sarvam was
silently truncating mid-response. Confirmed in production logs: battles
and AI Weekly Exam registrations kept ending up with zero generated
questions and getting cancelled, from exactly this call site raising
AIGenerationError("Sarvam AI did not return valid JSON.") on truncated
JSON ("Unterminated string...").
"""
from __future__ import annotations

import json

import pytest

from app.services.ai_provider import (
    AIGenerationError,
    AIResponse,
    SarvamAIProvider,
    _question_generation_max_tokens,
)


@pytest.fixture(autouse=True)
def _no_real_delay(monkeypatch):
    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr("app.services.ai_provider.asyncio.sleep", _instant_sleep)


def test_max_tokens_scales_with_question_count_and_stays_bounded():
    small = _question_generation_max_tokens(1)
    elimination = _question_generation_max_tokens(18)  # ELIMINATION_SINGLE_COUNT + ELIMINATE_MULTIPLE_COUNT
    ai_weekly = _question_generation_max_tokens(50)  # AI_WEEKLY_SINGLE_COUNT + AI_WEEKLY_MULTIPLE_COUNT

    assert small >= 2048  # never regresses below the old fixed value for tiny counts
    assert elimination > 2048  # the actual production failure case must now request more
    assert ai_weekly > elimination  # scales up, not a second fixed constant
    assert ai_weekly <= 12000  # stays within a sane ceiling rather than growing unbounded


async def test_generate_mixed_questions_passes_the_scaled_max_tokens_to_chat(monkeypatch):
    provider = SarvamAIProvider()
    captured = {}

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        captured["max_tokens"] = max_tokens
        payload = json.dumps([
            {"prompt": "Q1", "question_type": "single",
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    await provider.generate_mixed_questions("Topic", single_count=40, multiple_count=10)

    assert captured["max_tokens"] == _question_generation_max_tokens(50)
    assert captured["max_tokens"] > 2048


async def test_generate_questions_passes_the_scaled_max_tokens_to_chat(monkeypatch):
    provider = SarvamAIProvider()
    captured = {}

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        captured["max_tokens"] = max_tokens
        payload = json.dumps([
            {"prompt": "Q1", "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    await provider.generate_questions("Subject", count=12)

    assert captured["max_tokens"] == _question_generation_max_tokens(12)


async def test_truncated_json_that_never_recovers_still_raises_a_clear_error_after_retrying(monkeypatch):
    """Confirms a persistently truncated response still fails loudly and
    clearly rather than silently — after the retry (see the next test)
    gets its fair chance, not on the very first attempt."""
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        calls.append(1)
        return AIResponse(content='[{"prompt": "Q1", "options": [{"text": "unterminat', provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    with pytest.raises(AIGenerationError, match="valid JSON"):
        await provider.generate_mixed_questions("Topic", single_count=40, multiple_count=10)
    assert len(calls) == 2  # confirms it actually retried, not a single-shot failure


async def test_truncated_json_on_the_first_attempt_recovers_on_retry(monkeypatch):
    """Regression test: confirmed in production — a truncated/invalid-JSON
    response can come back well under the requested max_tokens budget (not
    the truncation the max_tokens scaling fixes), on a call that chat()'s
    own empty-response retry can't see, since the content wasn't empty,
    just malformed. Retrying the whole generate_mixed_questions call is
    what actually recovers it."""
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        calls.append(1)
        if len(calls) == 1:
            return AIResponse(content='[{"prompt": "Q1", "options": [{"text": "unterminat', provider="sarvam", tokens_used=10, latency_ms=5)
        payload = json.dumps([
            {"prompt": "Q1", "question_type": "single",
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    questions = await provider.generate_mixed_questions("Topic", single_count=1, multiple_count=0)

    assert len(calls) == 2
    assert len(questions) == 1
