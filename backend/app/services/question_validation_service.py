"""Structural validation for AI-generated questions before they're eligible
for any real exam/contest/battle. AI provider output already gets basic
shape checks in ai_provider.py's JSON parsing, but this is the second,
independent gate the spec asks for ("never send raw unvalidated AI output
directly into an exam") — it runs against the actual persisted Question
rows, checking for duplicates *within the generated batch* (something a
single provider call can't self-detect) and re-confirming answer-key
integrity before flipping is_validated.
"""
from __future__ import annotations

from app.services.ai_provider import GeneratedMCQ


class QuestionValidationError(Exception):
    pass


def validate_generated_batch(questions: list[GeneratedMCQ]) -> None:
    if not questions:
        raise QuestionValidationError("No questions were generated.")

    seen_prompts: set[str] = set()
    for q in questions:
        prompt_norm = q.prompt.strip().lower()
        if not prompt_norm:
            raise QuestionValidationError("A generated question has an empty prompt.")
        if prompt_norm in seen_prompts:
            raise QuestionValidationError(f"Duplicate question detected in the generated batch: {q.prompt[:80]!r}")
        seen_prompts.add(prompt_norm)

        if len(q.options) < 2:
            raise QuestionValidationError(f"Question has fewer than 2 options: {q.prompt[:80]!r}")
        option_texts = [text.strip().lower() for text, _ in q.options]
        if len(set(option_texts)) != len(option_texts):
            raise QuestionValidationError(f"Question has duplicate option text: {q.prompt[:80]!r}")
        if any(not text.strip() for text, _ in q.options):
            raise QuestionValidationError(f"Question has a blank option: {q.prompt[:80]!r}")

        correct_count = sum(1 for _, is_correct in q.options if is_correct)
        if q.question_type == "single" and correct_count != 1:
            raise QuestionValidationError(f"'single' question does not have exactly one correct option: {q.prompt[:80]!r}")
        if q.question_type == "multiple" and not (1 <= correct_count < len(q.options)):
            raise QuestionValidationError(f"'multiple' question has an invalid correct-option count: {q.prompt[:80]!r}")
