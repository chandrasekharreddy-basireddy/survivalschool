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

import re

from app.services.ai_provider import GeneratedMCQ

# Structural validation alone lets a successful prompt injection land
# verbatim in a real exam — this app's highest-blast-radius AI path, since
# generated content here is persisted with is_validated=True and served to
# every student registered for that topic, not sandboxed the way a chat
# response is. Two independent, narrow content-safety checks, neither of
# which requires guessing whether the *meaning* of the text was hijacked:
#
# 1. Reject markup outright. A jailbroken generation that injects HTML/script
#    content is caught here regardless of whether any frontend surface that
#    renders question text turns out to escape it correctly — defense in
#    depth, not a substitute for that escaping.
# 2. Reject text that talks ABOUT the generation prompt itself (leaked
#    system-prompt fragments, "ignore previous instructions" style phrases).
#    A real exam question never has a legitimate reason to contain either —
#    seeing one is a strong, low-false-positive signal the model's actual
#    output was hijacked rather than just generating a bad-quality question.
_HTML_TAG_RE = re.compile(r"<[a-zA-Z!/][^>]*>")
_INJECTION_MARKERS = (
    "ignore previous instructions", "ignore all previous", "disregard the above",
    "system prompt", "you are now", "act as", "new instructions:",
)


class QuestionValidationError(Exception):
    pass


def _check_content_safety(text: str, context: str) -> None:
    if _HTML_TAG_RE.search(text):
        raise QuestionValidationError(f"{context} contains markup, which real exam content never should: {text[:80]!r}")
    lowered = text.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            raise QuestionValidationError(f"{context} contains a suspicious instruction-like phrase ({marker!r}): {text[:80]!r}")


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
        _check_content_safety(q.prompt, "Question prompt")
        for text, _ in q.options:
            _check_content_safety(text, "Question option")

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
