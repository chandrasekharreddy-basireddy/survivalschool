from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.gamification import Achievement, Badge, PointsLedger, Streak
from app.models.user import User

router = APIRouter(prefix="/gamification", tags=["gamification"])


class MyStatsOut(BaseModel):
    total_points: int
    current_streak_days: int
    longest_streak_days: int
    badges: list[dict]


class LeaderboardEntry(BaseModel):
    rank: int
    student_id: uuid.UUID
    full_name: str
    total_points: int


@router.get("/me", response_model=MyStatsOut)
async def my_gamification_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(
        select(func.coalesce(func.sum(PointsLedger.amount), 0)).where(PointsLedger.student_id == user.id)
    )).scalar_one()
    streak = (await db.execute(select(Streak).where(Streak.student_id == user.id))).scalar_one_or_none()
    achievements = (await db.execute(
        select(Achievement, Badge).join(Badge, Badge.id == Achievement.badge_id).where(Achievement.student_id == user.id)
    )).all()
    return MyStatsOut(
        total_points=int(total),
        current_streak_days=streak.current_streak_days if streak else 0,
        longest_streak_days=streak.longest_streak_days if streak else 0,
        badges=[{"code": b.code, "name": b.name, "icon": b.icon, "awarded_at": a.awarded_at.isoformat()} for a, b in achievements],
    )


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(limit: int = Query(20, le=100), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PointsLedger.student_id, func.sum(PointsLedger.amount).label("total"))
        .group_by(PointsLedger.student_id)
        .order_by(func.sum(PointsLedger.amount).desc())
        .limit(limit)
    )
    rows = result.all()
    out = []
    for rank, (student_id, total) in enumerate(rows, start=1):
        student = await db.get(User, student_id)
        out.append(LeaderboardEntry(rank=rank, student_id=student_id, full_name=student.full_name if student else "Unknown", total_points=int(total)))
    return out
