from __future__ import annotations

from types import SimpleNamespace

from app.services.scoring_service import grade_answer, grade_short_answer, summarize_attempt


def _option(id_, is_correct):
    return SimpleNamespace(id=id_, is_correct=is_correct)


def test_single_choice_correct():
    question = SimpleNamespace(
        question_type="single", points=1, short_answer_key=None,
        options=[_option("a", True), _option("b", False)],
    )
    is_correct, points = grade_answer(question, ["a"], None)
    assert is_correct is True
    assert points == 1


def test_single_choice_wrong_selection_scores_zero_even_if_partially_right():
    question = SimpleNamespace(
        question_type="single", points=1, short_answer_key=None,
        options=[_option("a", True), _option("b", False)],
    )
    is_correct, points = grade_answer(question, ["b"], None)
    assert is_correct is False
    assert points == 0


def test_multiple_choice_requires_exact_set_match():
    question = SimpleNamespace(
        question_type="multiple", points=2, short_answer_key=None,
        options=[_option("a", True), _option("b", True), _option("c", False)],
    )
    partial = grade_answer(question, ["a"], None)
    assert partial == (False, 0)
    exact = grade_answer(question, ["a", "b"], None)
    assert exact == (True, 2)
    over_select = grade_answer(question, ["a", "b", "c"], None)
    assert over_select == (False, 0)


def test_short_answer_normalizes_whitespace_and_case():
    assert grade_short_answer("Paris", "  paris  ") == (True, 1)
    assert grade_short_answer("Paris", "PARIS") == (True, 1)
    assert grade_short_answer("Paris", "London") == (False, 0)
    assert grade_short_answer(None, "anything") == (False, 0)


def test_summarize_attempt_pass_fail_boundary():
    score, passed = summarize_attempt(7, 10, pass_score_percent=70)
    assert score == 70
    assert passed is True

    score, passed = summarize_attempt(6, 10, pass_score_percent=70)
    assert score == 60
    assert passed is False


def test_summarize_attempt_zero_possible_never_passes():
    score, passed = summarize_attempt(0, 0, pass_score_percent=70)
    assert score == 0
    assert passed is False
