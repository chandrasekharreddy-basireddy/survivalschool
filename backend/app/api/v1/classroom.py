from __future__ import annotations

import random
import string
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import (
    get_client_ip,
    get_current_user,
    get_current_verified_user,
    require_role,
)
from app.models.assessment import Question, QuestionOption
from app.models.classroom import (
    Classroom,
    ClassroomExam,
    ClassroomExamAnswer,
    ClassroomExamAttempt,
    ClassroomMember,
)
from app.models.user import User
from app.schemas.assessment import OptionPublicOut, QuestionPublicOut
from app.schemas.classroom import (
    ClassroomCreate,
    ClassroomExamAttemptOut,
    ClassroomExamAttemptStartOut,
    ClassroomExamCreate,
    ClassroomExamOut,
    ClassroomExamSubmit,
    ClassroomExamUpdate,
    ClassroomJoin,
    ClassroomMemberOut,
    ClassroomOut,
    ClassroomUpdate,
    IntegrityEventIn,
    IntegrityEventResponse,
    MyExamAttemptOut,
)

router = APIRouter(prefix="/classrooms", tags=["classrooms"])

MAX_FLAGGED_EVENTS = 200


def _generate_join_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def _get_classroom_or_404(db: AsyncSession, classroom_id: uuid.UUID) -> Classroom:
    classroom = await db.get(Classroom, classroom_id)
    if not classroom:
        raise NotFoundError("Classroom not found.")
    return classroom


async def _require_lecturer(classroom: Classroom, user: User) -> None:
    if not user.has_role("SUPER_ADMIN") and classroom.lecturer_id != user.id:
        raise AuthorizationError("You are not the lecturer of this classroom.")


async def _require_member_or_lecturer(db: AsyncSession, classroom: Classroom, user: User) -> None:
    if user.has_role("SUPER_ADMIN") or classroom.lecturer_id == user.id:
        return
    member = (await db.execute(
        select(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom.id,
            ClassroomMember.student_id == user.id,
            ClassroomMember.removed_at.is_(None),
        )
    )).scalar_one_or_none()
    if not member:
        raise AuthorizationError("You are not a member of this classroom.")


def _classroom_out(c: Classroom, lecturer_name: str = "", member_count: int = 0, exam_count: int = 0) -> ClassroomOut:
    return ClassroomOut(
        id=c.id, name=c.name, description=c.description, subject_id=c.subject_id,
        section=c.section, join_code=c.join_code, lecturer_id=c.lecturer_id,
        lecturer_name=lecturer_name, is_active=c.is_active,
        member_count=member_count, exam_count=exam_count, created_at=c.created_at,
    )


def _exam_out(e: ClassroomExam) -> ClassroomExamOut:
    return ClassroomExamOut(
        id=e.id, classroom_id=e.classroom_id, title=e.title, description=e.description,
        question_count=len(e.question_ids), duration_seconds=e.duration_seconds,
        starts_at=e.starts_at, ends_at=e.ends_at, status=e.status,
        fullscreen_required=e.fullscreen_required,
        integrity_monitoring_enabled=e.integrity_monitoring_enabled,
        max_warnings_before_terminate=e.max_warnings_before_terminate,
        face_proctoring_required=e.face_proctoring_required, created_at=e.created_at,
    )


# ── Lecturer endpoints ──


@router.post("", status_code=201)
async def create_classroom(
    body: ClassroomCreate,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ClassroomOut:
    code = _generate_join_code()
    while (await db.execute(select(Classroom).where(Classroom.join_code == code))).scalar_one_or_none():
        code = _generate_join_code()
    classroom = Classroom(
        name=body.name, description=body.description, subject_id=body.subject_id,
        section=body.section, join_code=code, lecturer_id=user.id,
    )
    db.add(classroom)
    await db.commit()
    await db.refresh(classroom)
    return _classroom_out(classroom, lecturer_name=user.full_name)


@router.get("/mine")
async def list_my_classrooms(
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[ClassroomOut]:
    rows = (await db.execute(
        select(Classroom).where(Classroom.lecturer_id == user.id).order_by(Classroom.created_at.desc())
    )).scalars().all()
    result = []
    for c in rows:
        mc = (await db.execute(
            select(func.count()).select_from(ClassroomMember).where(
                ClassroomMember.classroom_id == c.id, ClassroomMember.removed_at.is_(None)
            )
        )).scalar() or 0
        ec = (await db.execute(
            select(func.count()).select_from(ClassroomExam).where(ClassroomExam.classroom_id == c.id)
        )).scalar() or 0
        result.append(_classroom_out(c, lecturer_name=user.full_name, member_count=mc, exam_count=ec))
    return result


@router.put("/{classroom_id}")
async def update_classroom(
    classroom_id: uuid.UUID,
    body: ClassroomUpdate,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ClassroomOut:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(classroom, field, value)
    await db.commit()
    await db.refresh(classroom)
    return _classroom_out(classroom, lecturer_name=user.full_name)


@router.delete("/{classroom_id}/members/{student_id}", status_code=204)
async def remove_member(
    classroom_id: uuid.UUID,
    student_id: uuid.UUID,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> None:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    member = (await db.execute(
        select(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.student_id == student_id,
            ClassroomMember.removed_at.is_(None),
        )
    )).scalar_one_or_none()
    if not member:
        raise NotFoundError("Student not found in this classroom.")
    member.removed_at = datetime.now(UTC)
    await db.commit()


@router.post("/{classroom_id}/exams", status_code=201)
async def create_exam(
    classroom_id: uuid.UUID,
    body: ClassroomExamCreate,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ClassroomExamOut:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    status = "draft"
    if body.starts_at and body.ends_at:
        status = "scheduled"
    exam = ClassroomExam(
        classroom_id=classroom_id, title=body.title, description=body.description,
        question_ids=[str(qid) for qid in body.question_ids],
        duration_seconds=body.duration_seconds, starts_at=body.starts_at, ends_at=body.ends_at,
        status=status, created_by=user.id,
        fullscreen_required=body.fullscreen_required,
        integrity_monitoring_enabled=body.integrity_monitoring_enabled,
        max_integrity_violations=body.max_integrity_violations,
        max_warnings_before_terminate=body.max_warnings_before_terminate,
        face_proctoring_required=body.face_proctoring_required,
    )
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return _exam_out(exam)


@router.put("/{classroom_id}/exams/{exam_id}")
async def update_exam(
    classroom_id: uuid.UUID,
    exam_id: uuid.UUID,
    body: ClassroomExamUpdate,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ClassroomExamOut:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    exam = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == exam_id, ClassroomExam.classroom_id == classroom_id)
    )).scalar_one_or_none()
    if not exam:
        raise NotFoundError("Exam not found.")
    if exam.status not in ("draft", "scheduled"):
        raise ConflictError("Cannot edit an exam that is already open or closed.")
    update_data = body.model_dump(exclude_unset=True)
    if "question_ids" in update_data and update_data["question_ids"] is not None:
        update_data["question_ids"] = [str(qid) for qid in update_data["question_ids"]]
    for field, value in update_data.items():
        setattr(exam, field, value)
    if exam.starts_at and exam.ends_at and exam.status == "draft":
        exam.status = "scheduled"
    await db.commit()
    await db.refresh(exam)
    return _exam_out(exam)


@router.post("/{classroom_id}/exams/{exam_id}/publish", status_code=200)
async def publish_exam(
    classroom_id: uuid.UUID,
    exam_id: uuid.UUID,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> ClassroomExamOut:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    exam = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == exam_id, ClassroomExam.classroom_id == classroom_id)
    )).scalar_one_or_none()
    if not exam:
        raise NotFoundError("Exam not found.")
    if exam.status not in ("draft", "scheduled"):
        raise ConflictError("Exam is already published or closed.")
    if not exam.starts_at or not exam.ends_at:
        raise ConflictError("Set when joining opens and closes before publishing.")
    if not exam.question_ids:
        raise ConflictError("Add at least one question before publishing.")
    now = datetime.now(UTC)
    exam.status = "open" if now >= exam.starts_at else "scheduled"
    await db.commit()
    await db.refresh(exam)
    return _exam_out(exam)


@router.get("/{classroom_id}/exams/{exam_id}/results")
async def get_exam_results(
    classroom_id: uuid.UUID,
    exam_id: uuid.UUID,
    user: User = Depends(require_role("INSTRUCTOR", "ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> list[ClassroomExamAttemptOut]:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_lecturer(classroom, user)
    attempts = (await db.execute(
        select(ClassroomExamAttempt).where(ClassroomExamAttempt.exam_id == exam_id)
        .order_by(ClassroomExamAttempt.score_percent.desc().nullslast())
    )).scalars().all()
    result = []
    for a in attempts:
        student = await db.get(User, a.student_id)
        result.append(ClassroomExamAttemptOut(
            id=a.id, exam_id=a.exam_id, student_id=a.student_id,
            student_name=student.full_name if student else "",
            started_at=a.started_at, submitted_at=a.submitted_at,
            time_taken_seconds=a.time_taken_seconds, score_percent=a.score_percent,
            points_earned=a.points_earned, points_possible=a.points_possible,
            status=a.status, violation_count=a.violation_count, warning_count=a.warning_count,
        ))
    return result


# ── Student endpoints ──


@router.post("/join", status_code=200)
async def join_classroom(
    body: ClassroomJoin,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ClassroomOut:
    classroom = (await db.execute(
        select(Classroom).where(Classroom.join_code == body.join_code.upper(), Classroom.is_active.is_(True))
    )).scalar_one_or_none()
    if not classroom:
        raise NotFoundError("Invalid join code or classroom is inactive.")
    if classroom.lecturer_id == user.id:
        raise ConflictError("You are the lecturer of this classroom.")
    existing = (await db.execute(
        select(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom.id,
            ClassroomMember.student_id == user.id,
        )
    )).scalar_one_or_none()
    if existing:
        if existing.removed_at is None:
            raise ConflictError("You are already a member.")
        existing.removed_at = None
        await db.commit()
    else:
        db.add(ClassroomMember(classroom_id=classroom.id, student_id=user.id))
        await db.commit()
    lecturer = await db.get(User, classroom.lecturer_id)
    mc = (await db.execute(
        select(func.count()).select_from(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom.id, ClassroomMember.removed_at.is_(None)
        )
    )).scalar() or 0
    return _classroom_out(classroom, lecturer_name=lecturer.full_name if lecturer else "", member_count=mc)


@router.get("/enrolled")
async def list_enrolled_classrooms(
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClassroomOut]:
    memberships = (await db.execute(
        select(ClassroomMember).where(
            ClassroomMember.student_id == user.id, ClassroomMember.removed_at.is_(None)
        )
    )).scalars().all()
    result = []
    for m in memberships:
        classroom = await db.get(Classroom, m.classroom_id)
        if not classroom or not classroom.is_active:
            continue
        lecturer = await db.get(User, classroom.lecturer_id)
        mc = (await db.execute(
            select(func.count()).select_from(ClassroomMember).where(
                ClassroomMember.classroom_id == classroom.id, ClassroomMember.removed_at.is_(None)
            )
        )).scalar() or 0
        ec = (await db.execute(
            select(func.count()).select_from(ClassroomExam).where(
                ClassroomExam.classroom_id == classroom.id,
                ClassroomExam.status.in_(["scheduled", "open", "closed"]),
            )
        )).scalar() or 0
        result.append(_classroom_out(classroom, lecturer_name=lecturer.full_name if lecturer else "", member_count=mc, exam_count=ec))
    return result


@router.get("/{classroom_id}")
async def get_classroom(
    classroom_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClassroomOut:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_member_or_lecturer(db, classroom, user)
    lecturer = await db.get(User, classroom.lecturer_id)
    mc = (await db.execute(
        select(func.count()).select_from(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom.id, ClassroomMember.removed_at.is_(None)
        )
    )).scalar() or 0
    ec = (await db.execute(
        select(func.count()).select_from(ClassroomExam).where(ClassroomExam.classroom_id == classroom.id)
    )).scalar() or 0
    return _classroom_out(classroom, lecturer_name=lecturer.full_name if lecturer else "", member_count=mc, exam_count=ec)


@router.get("/{classroom_id}/members")
async def list_members(
    classroom_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClassroomMemberOut]:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_member_or_lecturer(db, classroom, user)
    members = (await db.execute(
        select(ClassroomMember).where(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.removed_at.is_(None),
        ).order_by(ClassroomMember.created_at)
    )).scalars().all()
    result = []
    for m in members:
        student = await db.get(User, m.student_id)
        result.append(ClassroomMemberOut(
            id=m.id, student_id=m.student_id,
            student_name=student.full_name if student else "",
            student_email=student.email if student else "",
            joined_at=m.created_at,
        ))
    return result


@router.get("/{classroom_id}/exams")
async def list_exams(
    classroom_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClassroomExamOut]:
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_member_or_lecturer(db, classroom, user)
    is_lecturer = user.has_role("SUPER_ADMIN") or classroom.lecturer_id == user.id
    query = select(ClassroomExam).where(ClassroomExam.classroom_id == classroom_id)
    if not is_lecturer:
        query = query.where(ClassroomExam.status.in_(["scheduled", "open", "closed"]))
    exams = (await db.execute(query.order_by(ClassroomExam.created_at.desc()))).scalars().all()
    return [_exam_out(e) for e in exams]


def _attempt_start_out(attempt: ClassroomExamAttempt, exam: ClassroomExam, now: datetime) -> ClassroomExamAttemptStartOut:
    """Every field here is a pure function of (exam, attempt, now) -- exam_starts_at
    and server_deadline_at are fixed the instant a student joins (both derived from
    exam.ends_at, the same instant for every student), so re-calling this for an
    existing attempt on page refresh always reports the same schedule. `status` is
    reported as whichever of waiting/in_progress is actually true for `now`, rather
    than trusting the DB row's status column, which only flips from waiting to
    in_progress lazily (the first time the student's client asks for questions)."""
    # exam.ends_at is guaranteed set here: an attempt only ever exists for an
    # exam that has already been published (start_attempt refuses to create
    # one for a "draft" exam), and publishing itself requires both
    # starts_at/ends_at to be set (see the publish check further up this
    # file). Narrows the type for the arithmetic below.
    assert exam.ends_at is not None
    if attempt.status in ("submitted", "terminated"):
        effective_status = attempt.status
    else:
        effective_status = "in_progress" if now >= exam.ends_at else "waiting"
    seconds_until_start = max(0, int((exam.ends_at - now).total_seconds()))
    remaining = max(0, int((attempt.server_deadline_at - now).total_seconds())) if effective_status == "in_progress" else 0
    return ClassroomExamAttemptStartOut(
        attempt_id=attempt.id, status=effective_status, exam_starts_at=exam.ends_at,
        server_deadline_at=attempt.server_deadline_at,
        seconds_until_start=seconds_until_start, remaining_seconds=remaining,
    )


@router.post("/{classroom_id}/exams/{exam_id}/attempts", status_code=201)
async def start_attempt(
    classroom_id: uuid.UUID,
    exam_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ClassroomExamAttemptStartOut:
    """Joining an exam and taking it are deliberately two different moments. The
    lecturer sets a join window [starts_at, ends_at]: students may join any time
    in that window, but nobody's timer starts early and nobody who joins late gets
    shortchanged -- every attempt's clock starts at the SAME instant (ends_at, when
    joining closes) and runs for the full duration_seconds from there. That instant
    is fixed here at join time (identically for every student), not computed later,
    so there's no separate "start the exam for everyone" step to run."""
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_member_or_lecturer(db, classroom, user)
    exam = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == exam_id, ClassroomExam.classroom_id == classroom_id)
    )).scalar_one_or_none()
    if not exam:
        raise NotFoundError("Exam not found.")
    now = datetime.now(UTC)
    if exam.status == "draft":
        raise ConflictError("This exam is not yet published.")
    if exam.status == "closed":
        raise ConflictError("This exam is closed.")
    if exam.starts_at and now < exam.starts_at:
        raise ConflictError("Joining hasn't opened yet.")
    if not exam.ends_at or now > exam.ends_at:
        raise ConflictError("Joining has closed for this exam.")

    existing = (await db.execute(
        select(ClassroomExamAttempt).where(
            ClassroomExamAttempt.exam_id == exam_id,
            ClassroomExamAttempt.student_id == user.id,
        )
    )).scalar_one_or_none()
    if existing:
        if existing.status in ("submitted", "terminated"):
            raise ConflictError("You have already submitted this exam.")
        return _attempt_start_out(existing, exam, now)

    question_order = list(exam.question_ids)
    random.shuffle(question_order)
    # Every student who joins gets the exam's full duration -- their clock starts
    # when joining closes (exam.ends_at), not when they clicked join, so someone
    # who joins a second before the deadline gets exactly the same time as someone
    # who joined when the window opened.
    deadline = exam.ends_at + timedelta(seconds=exam.duration_seconds)
    # status stays the model default ("in_progress") even while the student is
    # still in the pre-start waiting room -- "has this attempt actually started"
    # is answered purely by `now >= started_at` (checked by every endpoint below
    # that would let them see questions, answer, or be flagged for integrity
    # violations), not by a distinct status value.
    attempt = ClassroomExamAttempt(
        exam_id=exam_id, student_id=user.id, question_order=question_order,
        started_at=exam.ends_at, server_deadline_at=deadline,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return _attempt_start_out(attempt, exam, now)


@router.get("/{classroom_id}/exams/{exam_id}/attempts/me")
async def my_exam_attempt(
    classroom_id: uuid.UUID,
    exam_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MyExamAttemptOut | None:
    """Lets the exam page tell "I haven't joined this exam" apart from "I
    already finished it" on a fresh page load/refresh -- without this, a
    student revisiting the page after the join window closed (or just
    reloading after submitting) saw the same generic "this exam is closed"
    message as someone who never attempted it at all, with no way to see
    their score. Returns null, not a 404, when there's genuinely no
    attempt yet -- that's an expected, normal state for this endpoint, not
    an error."""
    classroom = await _get_classroom_or_404(db, classroom_id)
    await _require_member_or_lecturer(db, classroom, user)
    exam = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == exam_id, ClassroomExam.classroom_id == classroom_id)
    )).scalar_one_or_none()
    if not exam:
        raise NotFoundError("Exam not found.")
    attempt = (await db.execute(
        select(ClassroomExamAttempt).where(ClassroomExamAttempt.exam_id == exam_id, ClassroomExamAttempt.student_id == user.id)
    )).scalar_one_or_none()
    if attempt is None:
        return None
    base = _attempt_start_out(attempt, exam, datetime.now(UTC))
    return MyExamAttemptOut(
        **base.model_dump(),
        score_percent=attempt.score_percent, points_earned=attempt.points_earned, points_possible=attempt.points_possible,
    )


@router.get("/exams/attempts/{attempt_id}/questions")
async def get_attempt_questions(
    attempt_id: uuid.UUID,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionPublicOut]:
    attempt = await db.get(ClassroomExamAttempt, attempt_id)
    if not attempt or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        raise ConflictError("This attempt has already been submitted.")
    now = datetime.now(UTC)
    if now < attempt.started_at:
        raise ConflictError("The exam hasn't started yet — hang tight, it begins automatically once joining closes.", code="exam_not_started")
    if now > attempt.server_deadline_at:
        attempt.status = "submitted"
        attempt.submitted_at = now
        await db.commit()
        raise ConflictError("Your exam time has expired.")
    result = []
    for qid_str in attempt.question_order:
        q = await db.get(Question, uuid.UUID(qid_str))
        if not q:
            continue
        options = (await db.execute(
            select(QuestionOption).where(QuestionOption.question_id == q.id).order_by(QuestionOption.order_index)
        )).scalars().all()
        result.append(QuestionPublicOut(
            id=q.id, prompt=q.prompt, question_type=q.question_type, points=q.points,
            options=[OptionPublicOut(id=o.id, text=o.text, order_index=o.order_index) for o in options],
        ))
    return result


@router.post("/exams/attempts/{attempt_id}/submit")
async def submit_attempt(
    attempt_id: uuid.UUID,
    body: ClassroomExamSubmit,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ClassroomExamAttemptOut:
    attempt = await db.get(ClassroomExamAttempt, attempt_id)
    if not attempt or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        raise ConflictError("This attempt has already been submitted.")
    now = datetime.now(UTC)
    if now < attempt.started_at:
        raise ConflictError("The exam hasn't started yet.", code="exam_not_started")
    total_earned = 0
    total_possible = 0
    for ans in body.answers:
        q_result = await db.execute(
            select(Question).where(Question.id == ans.question_id).options(selectinload(Question.options))
        )
        q = q_result.scalar_one_or_none()
        if not q or str(q.id) not in attempt.question_order:
            continue
        from app.services.scoring_service import grade_answer
        correct, points = grade_answer(q, [str(oid) for oid in ans.selected_option_ids], ans.text_answer)
        total_earned += points
        total_possible += q.points
        db.add(ClassroomExamAnswer(
            attempt_id=attempt.id, question_id=q.id,
            selected_option_ids=[str(oid) for oid in ans.selected_option_ids],
            is_correct=correct, points_awarded=points,
        ))
    attempt.status = "submitted"
    attempt.submitted_at = now
    attempt.time_taken_seconds = int((now - attempt.started_at).total_seconds())
    attempt.points_earned = total_earned
    attempt.points_possible = total_possible
    attempt.score_percent = round(total_earned * 100 / total_possible) if total_possible > 0 else 0
    await db.commit()
    await db.refresh(attempt)
    student = await db.get(User, attempt.student_id)
    return ClassroomExamAttemptOut(
        id=attempt.id, exam_id=attempt.exam_id, student_id=attempt.student_id,
        student_name=student.full_name if student else "",
        started_at=attempt.started_at, submitted_at=attempt.submitted_at,
        time_taken_seconds=attempt.time_taken_seconds, score_percent=attempt.score_percent,
        points_earned=attempt.points_earned, points_possible=attempt.points_possible,
        status=attempt.status, violation_count=attempt.violation_count, warning_count=attempt.warning_count,
    )


@router.put("/exams/attempts/{attempt_id}/events")
async def report_integrity_event(
    attempt_id: uuid.UUID,
    body: IntegrityEventIn,
    request: Request,
    user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrityEventResponse:
    attempt = await db.get(ClassroomExamAttempt, attempt_id)
    if not attempt or attempt.student_id != user.id:
        raise NotFoundError("Attempt not found.")
    if attempt.status != "in_progress":
        return IntegrityEventResponse(recorded=False, terminated=attempt.status == "terminated")
    if datetime.now(UTC) < attempt.started_at:
        # Still in the pre-start waiting room -- nothing to flag yet.
        return IntegrityEventResponse(recorded=False)

    exam = await db.get(ClassroomExam, attempt.exam_id)
    if not exam or not exam.integrity_monitoring_enabled:
        return IntegrityEventResponse(recorded=False)

    if body.device_fingerprint and attempt.device_fingerprint:
        if body.device_fingerprint != attempt.device_fingerprint:
            attempt.status = "terminated"
            attempt.submitted_at = datetime.now(UTC)
            attempt.time_taken_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
            if len(attempt.flagged_events) < MAX_FLAGGED_EVENTS:
                attempt.flagged_events = [*attempt.flagged_events, {
                    "type": "device_change", "detail": "Device fingerprint mismatch",
                    "at": datetime.now(UTC).isoformat(),
                }]
            await db.commit()
            return IntegrityEventResponse(recorded=True, terminated=True)
    elif body.device_fingerprint and not attempt.device_fingerprint:
        attempt.device_fingerprint = body.device_fingerprint

    client_ip = get_client_ip(request)
    if attempt.allowed_ip and client_ip and client_ip != attempt.allowed_ip:
        attempt.status = "terminated"
        attempt.submitted_at = datetime.now(UTC)
        attempt.time_taken_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
        if len(attempt.flagged_events) < MAX_FLAGGED_EVENTS:
            attempt.flagged_events = [*attempt.flagged_events, {
                "type": "network_change", "detail": "IP address changed mid-exam",
                "at": datetime.now(UTC).isoformat(),
            }]
        await db.commit()
        return IntegrityEventResponse(recorded=True, terminated=True)
    elif client_ip and not attempt.allowed_ip:
        attempt.allowed_ip = client_ip

    attempt.violation_count += 1
    if len(attempt.flagged_events) < MAX_FLAGGED_EVENTS:
        attempt.flagged_events = [*attempt.flagged_events, {
            "type": body.event_type, "detail": body.detail,
            "at": datetime.now(UTC).isoformat(),
        }]

    if attempt.warning_count < exam.max_warnings_before_terminate:
        attempt.warning_count += 1
        await db.commit()
        return IntegrityEventResponse(
            recorded=True, warning=True,
            warnings_remaining=exam.max_warnings_before_terminate - attempt.warning_count,
        )

    attempt.status = "terminated"
    attempt.submitted_at = datetime.now(UTC)
    attempt.time_taken_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
    await db.commit()
    return IntegrityEventResponse(recorded=True, terminated=True)


# ── Admin overview ──


@router.get("/admin/stats")
async def classroom_admin_stats(
    user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    total = (await db.execute(select(func.count()).select_from(Classroom))).scalar() or 0
    active = (await db.execute(
        select(func.count()).select_from(Classroom).where(Classroom.is_active.is_(True))
    )).scalar() or 0
    total_exams = (await db.execute(select(func.count()).select_from(ClassroomExam))).scalar() or 0
    open_exams = (await db.execute(
        select(func.count()).select_from(ClassroomExam).where(ClassroomExam.status == "open")
    )).scalar() or 0
    return {"total_classrooms": total, "active_classrooms": active, "total_exams": total_exams, "open_exams": open_exams}
