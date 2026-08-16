from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import Profile, Role, User
from app.schemas.auth import MessageResponse, UserOut
from app.security.passwords import verify_password
from app.services.gdpr_service import delete_account, export_user_data

router = APIRouter(prefix="/users", tags=["users"])


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_email_verified=user.is_email_verified,
        is_active=user.is_active,
        roles=[r.name for r in user.roles],
    )


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.phone is not None:
        if not user.profile:
            user.profile = Profile(user_id=user.id)
        user.profile.phone = body.phone
    if body.bio is not None:
        if not user.profile:
            user.profile = Profile(user_id=user.id)
        user.profile.bio = body.bio
    if body.avatar_url is not None:
        if not user.profile:
            user.profile = Profile(user_id=user.id)
        user.profile.avatar_url = body.avatar_url
    await db.commit()
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_email_verified=user.is_email_verified,
        is_active=user.is_active,
        roles=[r.name for r in user.roles],
    )


@router.get("", response_model=list[UserOut])
async def list_users(
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).options(selectinload(User.roles)).where(User.deleted_at.is_(None))
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%") | User.full_name.ilike(f"%{q}%"))
    result = await db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    users = result.scalars().all()
    return [
        UserOut(id=u.id, email=u.email, full_name=u.full_name, is_email_verified=u.is_email_verified,
                is_active=u.is_active, roles=[r.name for r in u.roles])
        for u in users
    ]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")
    return UserOut(
        id=user.id, email=user.email, full_name=user.full_name,
        is_email_verified=user.is_email_verified, is_active=user.is_active,
        roles=[r.name for r in user.roles],
    )


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
    # V-01: Enforce role hierarchy — only SUPER_ADMIN can assign SUPER_ADMIN or ADMIN.
    # A plain ADMIN (who has "users.update" permission) must not be able to escalate.
    if role.name in ("SUPER_ADMIN", "ADMIN") and not admin_user.has_role("SUPER_ADMIN"):
        raise AuthorizationError("Insufficient privileges to assign this role.")
    if role not in target.roles:
        target.roles.append(role)
    await record_audit_event(db, actor_id=admin_user.id, action="user.role_assigned", resource_type="user",
                              resource_id=str(user_id), metadata={"role": role_name})
    await db.commit()
    return UserOut(id=target.id, email=target.email, full_name=target.full_name,
                    is_email_verified=target.is_email_verified, is_active=target.is_active,
                    roles=[r.name for r in target.roles])


@router.delete("/{user_id}/roles/{role_name}", response_model=UserOut)
async def remove_role(
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
    # V-01: Only SUPER_ADMIN can remove SUPER_ADMIN or ADMIN roles.
    if role.name in ("SUPER_ADMIN", "ADMIN") and not admin_user.has_role("SUPER_ADMIN"):
        raise AuthorizationError("Insufficient privileges to remove this role.")
    if role in target.roles:
        target.roles.remove(role)
    await record_audit_event(db, actor_id=admin_user.id, action="user.role_removed", resource_type="user",
                              resource_id=str(user_id), metadata={"role": role_name})
    await db.commit()
    return UserOut(id=target.id, email=target.email, full_name=target.full_name,
                    is_email_verified=target.is_email_verified, is_active=target.is_active,
                    roles=[r.name for r in target.roles])


@router.delete("/me", response_model=MessageResponse)
async def delete_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_account(db, user.id)
    await db.commit()
    return MessageResponse(message="Your account has been scheduled for deletion.")


@router.get("/me/export")
async def export_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await export_user_data(db, user.id)
    return Response(content=json.dumps(data, default=str, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=user-data-{user.id}.json"})
