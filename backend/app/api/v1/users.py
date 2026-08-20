from __future__ import annotations

import json
import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationAppError
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


class ProfileOut(BaseModel):
    id: uuid.UUID
    public_handle: str | None
    bio: str | None
    avatar_url: str | None
    timezone: str
    locale: str
    section: str | None

    model_config = {"from_attributes": True}


_HANDLE_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$")


class ProfilePatch(BaseModel):
    public_handle: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    timezone: str | None = None
    locale: str | None = None
    section: str | None = None


async def _get_or_create_profile(db: AsyncSession, user: User) -> Profile:
    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.get("/me/profile", response_model=ProfileOut)
async def get_my_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The caller's profile, created on first read so settings pages always
    have a row to edit."""
    return await _get_or_create_profile(db, user)


@router.patch("/me/profile", response_model=ProfileOut)
async def update_my_profile(
    body: ProfilePatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_or_create_profile(db, user)
    if body.public_handle is not None:
        handle = body.public_handle.strip().lower()
        if not _HANDLE_PATTERN.match(handle):
            raise ValidationAppError("Handles must be 3-30 characters: lowercase letters, numbers, and underscores only.")
        if handle != profile.public_handle:
            existing = (await db.execute(select(Profile).where(Profile.public_handle == handle))).scalar_one_or_none()
            if existing is not None and existing.id != profile.id:
                raise ConflictError("That handle is already taken.")
            profile.public_handle = handle
    if body.bio is not None:
        profile.bio = body.bio
    if body.avatar_url is not None:
        profile.avatar_url = body.avatar_url
    if body.timezone is not None:
        profile.timezone = body.timezone
    if body.locale is not None:
        profile.locale = body.locale
    if body.section is not None:
        profile.section = body.section
    await db.commit()
    await db.refresh(profile)
    return profile


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


class DeleteAccountRequest(BaseModel):
    password: str
    # Must be the literal string "DELETE" — a mistyped confirmation fails
    # validation (422) before any deletion is attempted.
    confirm: Literal["DELETE"]


@router.post("/me/delete-account", response_model=MessageResponse)
async def delete_my_account(
    payload: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete the caller's account and all associated data (GDPR
    erasure). Requires the current password and a typed "DELETE" confirmation.
    Deletion cascades to sessions and refresh tokens, so the access token used
    to make this call stops working immediately afterwards."""
    if not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Password is incorrect.")
    await delete_account(db, user)
    await db.commit()
    return MessageResponse(message="Your account and all associated data have been permanently deleted.")


@router.get("/me/export")
async def export_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await export_user_data(db, user)
    return Response(content=json.dumps(data, default=str, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=user-data-{user.id}.json"})
