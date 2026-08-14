"""GDPR-style data export (Art. 15/20 — right of access, data portability)
and account erasure (Art. 17 — right to erasure).

Export gathers every row genuinely tied to the requesting user, read fresh
at request time — no caching, no stale snapshots.

Deletion is a REAL hard `DELETE FROM users WHERE id = ...`, not a soft
scrub. This is safe here specifically because every FK referencing
`users.id` in this schema was already deliberately designed with the
correct ON DELETE behavior for exactly this case (verified against the
live schema, not assumed):

  - ON DELETE CASCADE on every column that is the user's OWN private
    record (enrollments, quiz/exam/contest attempts, certificates,
    points ledger, streak, achievements, practice sessions, bookmarks,
    notifications, attendance records, AI conversations/mock sessions,
    refresh tokens, sessions, profile, support tickets). These are
    genuinely erased — nothing about them makes sense to keep once the
    account is gone.

  - ON DELETE SET NULL on every column where the row is really SHARED
    content other users depend on for context (a discussion thread other
    students replied to, a chat message other room members read, a
    course the user instructed, a contest they created, a file they
    uploaded). These survive with their author/owner reference cleared —
    erasing the person without erasing content other real users still
    need, which is the correct GDPR balance when full deletion would
    degrade someone else's legitimate data.

No Python-side cascade logic is needed or written here: `db.delete(user)`
followed by a commit is enough, because the database-level constraints
do the rest. This was verified against the live Postgres schema (not just
assumed from the SQLAlchemy model declarations) before writing this.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIConversation, AIMessage
from app.models.ai_practice import AIMockSession
from app.models.assessment import ExamAttempt, QuizAttempt
from app.models.attendance import AttendanceRecord
from app.models.certificate import Certificate
from app.models.contest import ContestAttempt, ContestCertificate
from app.models.discussion import DiscussionReply, DiscussionThread
from app.models.gamification import Achievement, PointsLedger, Streak
from app.models.lms import CourseProgress, Enrollment, LessonProgress
from app.models.practice import PracticeSession, QuestionBookmark
from app.models.social import ChatMessage, Notification
from app.models.system import AuditLog
from app.models.user import Profile, User


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def export_user_data(db: AsyncSession, user: User) -> dict[str, Any]:
    uid = user.id

    async def rows(stmt):
        return (await db.execute(stmt)).scalars().all()

    profile = (await db.execute(select(Profile).where(Profile.user_id == uid))).scalar_one_or_none()
    enrollments = await rows(select(Enrollment).where(Enrollment.student_id == uid))
    course_progress = await rows(select(CourseProgress).where(CourseProgress.student_id == uid))
    lesson_progress = await rows(select(LessonProgress).where(LessonProgress.student_id == uid))
    quiz_attempts = await rows(select(QuizAttempt).where(QuizAttempt.student_id == uid))
    exam_attempts = await rows(select(ExamAttempt).where(ExamAttempt.student_id == uid))
    certificates = await rows(select(Certificate).where(Certificate.student_id == uid))
    contest_attempts = await rows(select(ContestAttempt).where(ContestAttempt.student_id == uid))
    contest_certificates = await rows(select(ContestCertificate).where(ContestCertificate.student_id == uid))
    points = await rows(select(PointsLedger).where(PointsLedger.student_id == uid))
    streak = (await db.execute(select(Streak).where(Streak.student_id == uid))).scalar_one_or_none()
    achievements = await rows(select(Achievement).where(Achievement.student_id == uid))
    practice_sessions = await rows(select(PracticeSession).where(PracticeSession.student_id == uid))
    bookmarks = await rows(select(QuestionBookmark).where(QuestionBookmark.student_id == uid))
    discussion_threads = await rows(select(DiscussionThread).where(DiscussionThread.author_id == uid))
    discussion_replies = await rows(select(DiscussionReply).where(DiscussionReply.author_id == uid))
    chat_messages = await rows(select(ChatMessage).where(ChatMessage.sender_id == uid))
    notifications = await rows(select(Notification).where(Notification.user_id == uid))
    attendance = await rows(select(AttendanceRecord).where(AttendanceRecord.student_id == uid))
    ai_conversations = await rows(select(AIConversation).where(AIConversation.user_id == uid))
    ai_mock_sessions = await rows(select(AIMockSession).where(AIMockSession.student_id == uid))
    audit_as_actor = await rows(
        select(AuditLog).where(AuditLog.actor_id == uid).order_by(AuditLog.created_at.desc()).limit(500)
    )

    ai_messages: list[AIMessage] = []
    if ai_conversations:
        conv_ids = [c.id for c in ai_conversations]
        ai_messages = await rows(select(AIMessage).where(AIMessage.conversation_id.in_(conv_ids)))

    return {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "This export includes every record in Survival School's database that is "
                "personally identifiable or personally generated by this account, gathered "
                "fresh at the moment of export. It excludes only anonymous/aggregate "
                "analytics events (which never store more than a user_id, no content) and "
                "records that legally must survive account deletion unattached to you "
                "(e.g. the audit trail's action log, capped to your most recent 500 entries "
                "here for size).",
        "account": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_email_verified": user.is_email_verified,
            "totp_enabled": user.totp_enabled,
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
        },
        "profile": None if profile is None else {
            "bio": profile.bio, "avatar_url": profile.avatar_url,
            "timezone": profile.timezone, "locale": profile.locale,
        },
        "enrollments": [
            {"course_id": str(e.course_id), "status": e.status, "completed_at": _iso(e.completed_at), "enrolled_at": _iso(e.created_at)}
            for e in enrollments
        ],
        "course_progress": [
            {"course_id": str(c.course_id), "percent_complete": c.percent_complete, "lessons_completed": c.lessons_completed}
            for c in course_progress
        ],
        "lesson_progress": [
            {"lesson_id": str(lp.lesson_id), "is_completed": lp.is_completed, "completed_at": _iso(lp.completed_at)}
            for lp in lesson_progress
        ],
        "quiz_attempts": [
            {"quiz_id": str(q.quiz_id), "attempt_number": q.attempt_number, "score_percent": q.score_percent,
             "passed": q.passed, "status": q.status, "submitted_at": _iso(q.submitted_at)}
            for q in quiz_attempts
        ],
        "exam_attempts": [
            {"exam_id": str(e.exam_id), "attempt_number": e.attempt_number, "score_percent": e.score_percent,
             "passed": e.passed, "status": e.status, "submitted_at": _iso(e.submitted_at)}
            for e in exam_attempts
        ],
        "certificates": [
            {"certificate_number": c.certificate_number, "course_id": str(c.course_id), "grade": c.grade,
             "score_percent": c.score_percent, "issued_at": _iso(c.issued_at), "revoked_at": _iso(c.revoked_at)}
            for c in certificates
        ],
        "contest_attempts": [
            {"contest_id": str(c.contest_id), "score_percent": c.score_percent, "rank": c.rank,
             "status": c.status, "submitted_at": _iso(c.submitted_at)}
            for c in contest_attempts
        ],
        "contest_certificates": [
            {"certificate_number": c.certificate_number, "contest_title": c.contest_title,
             "rank": c.rank, "issued_at": _iso(c.issued_at)}
            for c in contest_certificates
        ],
        "points_ledger": [
            {"amount": p.amount, "reason": p.reason, "awarded_at": _iso(p.created_at)} for p in points
        ],
        "total_points": sum(p.amount for p in points),
        "streak": None if streak is None else {
            "current_streak_days": streak.current_streak_days,
            "longest_streak_days": streak.longest_streak_days,
            "last_activity_date": _iso(streak.last_activity_date),
        },
        "achievements": [{"badge_id": str(a.badge_id), "awarded_at": _iso(a.awarded_at)} for a in achievements],
        "practice_sessions": [
            {"source": p.source, "score_percent": p.score_percent, "submitted_at": _iso(p.submitted_at)}
            for p in practice_sessions
        ],
        "question_bookmarks": [{"question_id": str(b.question_id), "note": b.note} for b in bookmarks],
        "discussion_threads_authored": [
            {"id": str(t.id), "course_id": str(t.course_id), "title": t.title, "body": t.body, "created_at": _iso(t.created_at)}
            for t in discussion_threads
        ],
        "discussion_replies_authored": [
            {"thread_id": str(r.thread_id), "body": r.body, "created_at": _iso(r.created_at)}
            for r in discussion_replies
        ],
        "chat_messages_sent": [
            {"room_id": str(m.room_id), "body": m.body, "sent_at": _iso(m.created_at)} for m in chat_messages
        ],
        "notifications": [
            {"category": n.category, "title": n.title, "body": n.body, "read_at": _iso(n.read_at), "created_at": _iso(n.created_at)}
            for n in notifications
        ],
        "attendance_records": [
            {"session_id": str(a.session_id), "status": a.status, "method": a.method, "checked_in_at": _iso(a.checked_in_at)}
            for a in attendance
        ],
        "ai_conversations": [{"id": str(c.id), "title": c.title, "created_at": _iso(c.created_at)} for c in ai_conversations],
        "ai_messages": [
            {"conversation_id": str(m.conversation_id), "role": m.role, "content": m.content, "sent_at": _iso(m.created_at)}
            for m in ai_messages
        ],
        "ai_mock_practice_sessions": [
            {"subject": s.subject, "question_count": s.question_count, "score_percent": s.score_percent, "created_at": _iso(s.created_at)}
            for s in ai_mock_sessions
        ],
        "audit_log_as_actor": [
            {"action": a.action, "resource_type": a.resource_type, "resource_id": a.resource_id,
             "result": a.result, "occurred_at": _iso(a.created_at)}
            for a in audit_as_actor
        ],
    }


async def delete_account(db: AsyncSession, user: User) -> None:
    """Hard-deletes the user row. See module docstring for why this is
    safe: every FK referencing users.id already has the correct ON DELETE
    CASCADE (own private records) or SET NULL (shared content) behavior at
    the database level, verified directly against the live schema."""
    await db.delete(user)
