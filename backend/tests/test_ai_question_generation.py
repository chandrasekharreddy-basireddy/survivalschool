"""Regression coverage for two real production bugs in Sarvam question
generation, confirmed by testing directly against the live API with a real
subscription key (not simulated):

1. SarvamAIProvider.chat() used to always request a fixed max_tokens=2048
   regardless of how much output was actually being asked for, while
   generate_mixed_questions asks for up to 50 questions (AI Weekly Exam) or
   18 (elimination battles) in one JSON response.

2. Scaling max_tokens up for that one big request could never actually fix
   it: sarvam-105b is a reasoning model that burns a large, largely fixed
   chunk of any max_tokens budget on internal chain-of-thought before
   writing the real answer, and the connected account's subscription tier
   hard-caps max_tokens at 4096 server-side (a higher value is rejected
   outright with a 400, not gracefully degraded). A single request for a
   full 18- or 50-question batch could never reliably fit regardless of how
   the cap was tuned.

Both are why battles and AI Weekly Exam registrations kept ending up with
zero generated questions and getting cancelled. The fix verified live: small
batches (a handful of questions per request) run concurrently reliably
complete within the account's token cap. generate_questions/
generate_mixed_questions now chunk their requested count into batches and
aggregate the results — these tests cover that chunking and aggregation.
"""
from __future__ import annotations

import json

import pytest

from app.services.ai_provider import (
    AIGenerationError,
    AIResponse,
    SarvamAIProvider,
    _BATCH_MAX_TOKENS,
    _chunk_counts,
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
    assert ai_weekly >= elimination  # scales up, not a second fixed constant
    # The connected account's subscription tier hard-caps max_tokens at 4096
    # server-side (confirmed live: a >4096 request is rejected outright with
    # a 400) — this must never return a value the account would reject.
    assert ai_weekly <= 4096


def test_chunk_counts_splits_into_batches_with_a_remainder():
    assert _chunk_counts(18, 5) == [5, 5, 5, 3]
    assert _chunk_counts(10, 5) == [5, 5]
    assert _chunk_counts(1, 5) == [1]
    assert _chunk_counts(0, 5) == []


async def test_generate_mixed_questions_splits_a_large_count_into_batches(monkeypatch):
    """The actual elimination-battle shape: 12 single + 6 multiple = 18
    questions, comfortably more than one batch. Confirms every batch
    request stays within the per-batch token budget (never the old
    count-scaled value, which the account would reject above 4096) and the
    per-batch results get aggregated into the full set."""
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        calls.append({"max_tokens": max_tokens, "content": messages[0]["content"]})
        # Reply with as many questions as the batch's own prompt asked for,
        # so the aggregate count below can be checked precisely.
        requested = int(messages[0]["content"].split("Generate exactly ")[1].split(" ")[0])
        qtype = "multiple" if "multi-select" in messages[0]["content"] else "single"
        payload = json.dumps([
            {"prompt": f"Q{i}-{qtype}", "question_type": qtype,
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]}
            for i in range(requested)
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    questions = await provider.generate_mixed_questions("Topic", single_count=12, multiple_count=6)

    assert len(questions) == 18
    assert len(calls) > 1  # confirms it actually batched, not one big request
    assert all(call["max_tokens"] == _BATCH_MAX_TOKENS for call in calls)
    assert all(call["max_tokens"] <= 4096 for call in calls)


async def test_generate_questions_splits_a_large_count_into_batches(monkeypatch):
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        calls.append(max_tokens)
        requested = int(messages[0]["content"].split("Generate exactly ")[1].split(" ")[0])
        payload = json.dumps([
            {"prompt": f"Q{i}", "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]}
            for i in range(requested)
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    questions = await provider.generate_questions("Subject", count=12)

    assert len(questions) == 12
    assert len(calls) > 1
    assert all(mt == _BATCH_MAX_TOKENS for mt in calls)


async def test_a_single_small_batch_still_requests_within_the_cap(monkeypatch):
    """count=1 fits in exactly one batch — confirms the batching change
    didn't regress the simple, common case of a small request."""
    provider = SarvamAIProvider()
    captured = {}

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        captured["max_tokens"] = max_tokens
        payload = json.dumps([
            {"prompt": "Q1", "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    questions = await provider.generate_questions("Subject", count=1)

    assert len(questions) == 1
    assert captured["max_tokens"] == _BATCH_MAX_TOKENS
    assert captured["max_tokens"] <= 4096


async def test_truncated_json_that_never_recovers_still_raises_a_clear_error_after_retrying(monkeypatch):
    """Confirms a persistently truncated response still fails loudly and
    clearly rather than silently — after the retry (see the next test)
    gets its fair chance, not on the very first attempt. Scoped to a count
    that produces exactly one batch so the call count stays simple to
    assert."""
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        calls.append(1)
        return AIResponse(content='[{"prompt": "Q1", "options": [{"text": "unterminat', provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    with pytest.raises(AIGenerationError, match="valid JSON"):
        await provider.generate_mixed_questions("Topic", single_count=3, multiple_count=0)
    assert len(calls) == 2  # confirms it actually retried, not a single-shot failure


async def test_truncated_json_on_the_first_attempt_recovers_on_retry(monkeypatch):
    """Regression test: confirmed in production — a truncated/invalid-JSON
    response can come back well under the requested max_tokens budget (not
    the truncation the max_tokens scaling fixes), on a call that chat()'s
    own empty-response retry can't see, since the content wasn't empty,
    just malformed. Retrying the whole batch is what actually recovers it."""
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


async def test_a_failed_batch_fails_the_whole_generation(monkeypatch):
    """A partial question pool isn't a usable one — if any batch never
    recovers, the whole generate_mixed_questions call must raise rather
    than silently returning fewer questions than requested."""
    provider = SarvamAIProvider()

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        if "multi-select" in messages[0]["content"]:
            return AIResponse(content='not json at all', provider="sarvam", tokens_used=10, latency_ms=5)
        payload = json.dumps([
            {"prompt": "Q1", "question_type": "single",
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    with pytest.raises(AIGenerationError, match="valid JSON"):
        await provider.generate_mixed_questions("Topic", single_count=1, multiple_count=1)


async def test_duplicate_prompts_across_batches_get_topped_up_not_dropped(monkeypatch):
    """Regression test for a real failure confirmed against the live
    Sarvam API: two separate batches for the same topic ("Object-Oriented
    Programming") independently generated the exact same obvious question
    ("What is abstraction in object-oriented programming?"), which
    validate_generated_batch() then rejected outright — cancelling the
    whole elimination battle even though 17 of the 18 questions were
    perfectly fine. The fix must detect the collision itself (no DB/
    validator involved here) and request exactly one replacement instead
    of silently returning fewer questions than asked for."""
    provider = SarvamAIProvider()
    calls = []

    async def fake_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        content = messages[0]["content"]
        calls.append(content)
        qtype = "multiple" if "multi-select" in content else "single"
        if "Do not repeat" not in content:
            prompt = "Duplicate question text"
        else:
            prompt = "A fresh, different question"
        payload = json.dumps([
            {"prompt": prompt, "question_type": qtype,
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]},
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", fake_chat)
    questions = await provider.generate_mixed_questions("Topic", single_count=1, multiple_count=1)

    assert len(questions) == 2
    prompts = {q.prompt.strip().lower() for q in questions}
    assert len(prompts) == 2  # no duplicates survived
    assert len(calls) > 2  # confirms a top-up round actually ran


async def test_persistent_duplicates_raise_instead_of_returning_too_few(monkeypatch):
    """If the model keeps colliding on the same prompt even after the
    top-up attempts are exhausted, this must fail loudly (a partial
    question pool the caller doesn't know is short is worse than a clear
    error) rather than silently handing back fewer questions than asked
    for."""
    provider = SarvamAIProvider()

    async def always_duplicate_chat(messages, *, system_prompt=None, image_data_url=None, max_tokens=2048):
        content = messages[0]["content"]
        qtype = "multiple" if "multi-select" in content else "single"
        requested = int(content.split("Generate exactly ")[1].split(" ")[0])
        payload = json.dumps([
            {"prompt": "Same question always", "question_type": qtype,
             "options": [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]}
            for _ in range(requested)
        ])
        return AIResponse(content=payload, provider="sarvam", tokens_used=10, latency_ms=5)

    monkeypatch.setattr(provider, "chat", always_duplicate_chat)
    with pytest.raises(AIGenerationError, match="duplicate"):
        await provider.generate_mixed_questions("Topic", single_count=2, multiple_count=0)
