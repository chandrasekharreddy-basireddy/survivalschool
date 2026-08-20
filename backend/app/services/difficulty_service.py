"""Topic difficulty scoring for AI Weekly Exam registration eligibility
(spec: registration requires the selected topic to meet a 70% difficulty
threshold).

Deliberately NOT a single opaque "ask an LLM for a percentage" call — that
produces an unfalsifiable number nobody can audit or reproduce. Instead this
is a real, documented formula over data already in the database:

    difficulty_percent = round(
        0.5 * complexity_component +
        0.5 * historical_miss_rate_component
    )

- complexity_component (0-100): derived from the topic's validated
  questions — average option count (more options = more discriminating,
  capped contribution) and the proportion of "multiple"-type (MSQ)
  questions (harder than single-answer by construction, since every
  correct option must be identified). Formula:
    complexity = min(100, (avg_option_count - 2) * 20 + msq_fraction * 40)
  With 2 options -> 0 base, 4 options -> 40 base; a topic that's entirely
  MSQ adds up to another 40.
- historical_miss_rate_component (0-100): the fraction of past answers on
  this topic's questions (across ContestAnswer + PracticeAnswer) that were
  wrong, i.e. real observed student performance. Topics with no history
  yet fall back to the complexity component alone (sample_size=0), so a
  brand-new topic isn't unfairly scored as "easy" just because nobody has
  attempted it.

Every evaluation is persisted with its formula_version and a human-readable
`reason` string explaining the actual numbers that produced the score, so
"why is this topic 74% difficult" always has a real, reproducible answer.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Question, QuestionOption
from app.models.contest import ContestAnswer
from app.models.exam_platform import TopicDifficultyEvaluation
from app.models.practice import PracticeAnswer

FORMULA_VERSION = "v1"
MIN_DIFFICULTY_PERCENT_FOR_AI_EXAM = 70


async def evaluate_topic_difficulty(db: AsyncSession, topic_id: uuid.UUID) -> TopicDifficultyEvaluation:
    question_ids = (await db.execute(
        select(Question.id).where(Question.topic_id == topic_id, Question.is_validated.is_(True))
    )).scalars().all()

    if not question_ids:
        evaluation = TopicDifficultyEvaluation(
            topic_id=topic_id, difficulty_percent=0, formula_version=FORMULA_VERSION,
            reason="No validated questions exist for this topic yet.", sample_size=0,
        )
    else:
        avg_option_count = (await db.execute(
            select(func.avg(func.count(QuestionOption.id)))
            .select_from(QuestionOption)
            .where(QuestionOption.question_id.in_(question_ids))
            .group_by(QuestionOption.question_id)
        )).scalar() or 2.0
        msq_count = (await db.execute(
            select(func.count()).select_from(Question).where(Question.id.in_(question_ids), Question.question_type == "multiple")
        )).scalar_one()
        msq_fraction = msq_count / len(question_ids)
        complexity = min(100.0, max(0.0, (float(avg_option_count) - 2) * 20 + msq_fraction * 40))

        contest_answers = (await db.execute(
            select(ContestAnswer.is_correct).where(ContestAnswer.question_id.in_(question_ids))
        )).scalars().all()
        practice_answers = (await db.execute(
            select(PracticeAnswer.is_correct).where(PracticeAnswer.question_id.in_(question_ids))
        )).scalars().all()
        all_answers = [a for a in (list(contest_answers) + list(practice_answers)) if a is not None]

        if all_answers:
            miss_rate = sum(1 for a in all_answers if not a) / len(all_answers) * 100
            difficulty = round(0.5 * complexity + 0.5 * miss_rate)
            reason = (
                f"{len(question_ids)} validated question(s), avg {float(avg_option_count):.1f} options, "
                f"{msq_fraction:.0%} multi-select -> complexity {complexity:.0f}%. "
                f"{len(all_answers)} historical answer(s), {miss_rate:.0f}% wrong -> "
                f"difficulty = round(0.5*{complexity:.0f} + 0.5*{miss_rate:.0f}) = {difficulty}%."
            )
        else:
            difficulty = round(complexity)
            reason = (
                f"{len(question_ids)} validated question(s), avg {float(avg_option_count):.1f} options, "
                f"{msq_fraction:.0%} multi-select -> complexity {complexity:.0f}%. "
                f"No historical answers yet, so difficulty = complexity component only = {difficulty}%."
            )

        evaluation = TopicDifficultyEvaluation(
            topic_id=topic_id, difficulty_percent=int(difficulty), formula_version=FORMULA_VERSION,
            reason=reason, sample_size=len(all_answers),
        )

    # Supersede any prior evaluation for this topic rather than deleting it —
    # history stays queryable, only the "current" flag moves.
    await db.execute(
        TopicDifficultyEvaluation.__table__.update()
        .where(TopicDifficultyEvaluation.topic_id == topic_id, TopicDifficultyEvaluation.is_current.is_(True))
        .values(is_current=False)
    )
    db.add(evaluation)
    await db.flush()
    return evaluation


async def get_current_difficulty(db: AsyncSession, topic_id: uuid.UUID) -> TopicDifficultyEvaluation:
    current = (await db.execute(
        select(TopicDifficultyEvaluation)
        .where(TopicDifficultyEvaluation.topic_id == topic_id, TopicDifficultyEvaluation.is_current.is_(True))
    )).scalar_one_or_none()
    if current is not None:
        return current
    return await evaluate_topic_difficulty(db, topic_id)
