from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai,
    analytics,
    auth,
    certificates,
    chat,
    courses,
    discussions,
    exams,
    files,
    gamification,
    health,
    lessons,
    notifications,
    practice,
    quizzes,
    search,
    timetable,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(courses.router)
api_router.include_router(lessons.router)
api_router.include_router(quizzes.router)
api_router.include_router(quizzes.questions_router)
api_router.include_router(exams.router)
api_router.include_router(certificates.router)
api_router.include_router(files.router)
api_router.include_router(gamification.router)
api_router.include_router(notifications.router)
api_router.include_router(chat.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
api_router.include_router(admin.router)
api_router.include_router(timetable.router)
api_router.include_router(discussions.router)
api_router.include_router(practice.router)
api_router.include_router(search.router)
