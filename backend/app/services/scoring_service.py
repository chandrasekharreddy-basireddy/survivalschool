"""Server-authoritative scoring for quizzes and exams.

Spec sections 14/15 are explicit: "Never trust client-submitted scores."
This module is the only place that decides whether an answer is correct and
how many points it earns — it is never handed a score from the client, only
raw selected option IDs / free text, which it grades itself against the
Question/QuestionOption rows.
"""
from __future__ import annotations


def grade_single_or_multiple(question_options: list, selected_option_ids: list[str]) -> tuple[bool, int]:
    correct_ids = {str(o.id) for o in question_options if o.is_correct}
    selected_ids = set(selected_option_ids)
    is_correct = correct_ids == selected_ids and len(correct_ids) > 0
    return is_correct, 1 if is_correct else 0


def grade_true_false(question_options: list, selected_option_ids: list[str]) -> tuple[bool, int]:
    return grade_single_or_multiple(question_options, selected_option_ids)


def grade_short_answer(expected: str | None, given: str | None) -> tuple[bool, int]:
    if not expected or not given:
        return False, 0

    def normalize(s: str) -> str:
        return " ".join(s.strip().lower().split())

    is_correct = normalize(expected) == normalize(given)
    return is_correct, 1 if is_correct else 0


def grade_answer(question, selected_option_ids: list[str], text_answer: str | None) -> tuple[bool, int]:
    """Returns (is_correct, points_awarded) for one question, fully server-side."""
    if question.question_type in ("single", "multiple", "true_false"):
        is_correct, _ = grade_single_or_multiple(question.options, selected_option_ids)
    elif question.question_type == "short_answer":
        is_correct, _ = grade_short_answer(question.short_answer_key, text_answer)
    else:
        is_correct = False
    points = question.points if is_correct else 0
    return is_correct, points


def summarize_attempt(points_earned: int, points_possible: int, pass_score_percent: int) -> tuple[int, bool]:
    if points_possible <= 0:
        return 0, False
    score_percent = round((points_earned / points_possible) * 100)
    return score_percent, score_percent >= pass_score_percent
