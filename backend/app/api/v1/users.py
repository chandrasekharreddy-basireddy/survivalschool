from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import Profile, Role, User
from app.schemas.auth import UserOut

router = APIRouter(prefix="/users", tags=["users"])


class ProfileUpdate(BaseModel):
    bio: str | None = None
    avatar_url: str | None = None
    timezone: str | None = None
    locale: str | None = None


class ProfileOut(BaseModel):
    bio: str | None = None
    avatar_url: str | None = None
    timezone: str
    locale: str

    model_config = {"from_attributes": True}


@router.get("/me/profile", response_model=ProfileOut)
async def get_my_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.patch("/me/profile", response_model=ProfileOut)
async def update_my_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("", response_model=list[UserOut])
async def list_users(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).options(selectinload(User.roles)).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    result = await db.execute(stmt.limit(limit).offset(offset))
    users = result.scalars().all()
    return [UserOut(id=u.id, email=u.email, full_name=u.full_name, is_email_verified=u.is_email_verified,
                     roles=[r.name for r in u.roles]) for u in users]


@router.post("/{user_id}/roles/{role_name}", response_model=UserOut)
async def assign_role(
    user_id: uuid.UUID, role_name: str,
    admin_user: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit_service import record_audit_event

    target = (await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))).scalar_one_or_none()
    if target is None:
        raise NotFoundError("User not found.")
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    if role not in target.roles:
        target.roles.append(role)
    await record_audit_event(db, actor_id=admin_user.id, action="user.role_assigned", resource_type="user",
                              resource_id=str(user_id), metadata={"role": role_name})
    await db.commit()
    return UserOut(id=target.id, email=target.email, full_name=target.full_name,
                    is_email_verified=target.is_email_verified, roles=[r.name for r in target.roles])
