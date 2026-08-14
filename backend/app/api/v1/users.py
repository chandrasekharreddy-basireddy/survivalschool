from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthenticationError, NotFoundError, ValidationAppError
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import Profile, Role, User
from app.schemas.auth import MessageResponse, UserOut
from app.security.passwords import verify_password
from app.services.gdpr_service import delete_account, export_user_data

router = APIRouter(prefix="/users", tags=["users"])


class AccountDeleteIn(BaseModel):
    password: str
    confirm: str  # must be the literal string "DELETE" — a typed confirmation
    # gate, same UX bar as GitHub/most real account-deletion flows, on top
    # of the password check below.


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
                     is_active=u.is_active, roles=[r.name for r in u.roles]) for u in users]


@router.get("/me/export")
async def export_my_data(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """GDPR-style data export (Art. 15 right of access / Art. 20 data
    portability). Returned as a downloadable JSON file rather than a typed
    response_model — the export's shape is intentionally comprehensive and
    additive, not a fixed API contract other clients depend on."""
    from app.services.audit_service import record_audit_event

    data = await export_user_data(db, user)
    await record_audit_event(db, actor_id=user.id, action="user.data_exported", resource_type="user", resource_id=str(user.id))
    await db.commit()
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="survivalschool-data-export-{user.id}.json"'},
    )


@router.post("/me/delete-account", response_model=MessageResponse)
async def delete_my_account(payload: AccountDeleteIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Right to erasure (GDPR Art. 17). Requires the account password AND a
    typed "DELETE" confirmation — same two-factor-of-intent bar as
    POST /auth/2fa/disable's password check, plus a typed confirmation on
    top since this is irreversible where 2FA-disable is not. See
    app/services/gdpr_service.py for exactly what is erased vs. anonymized
    and why (the DB's own FK design already encodes the correct answer)."""
    if payload.confirm != "DELETE":
        raise ValidationAppError('Type "DELETE" to confirm.')
    if not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Incorrect password.")

    from app.services.audit_service import record_audit_event

    # Recorded before deletion — audit_logs.actor_id has no FK constraint
    # back to users (deliberately, so the trail outlives the account), so
    # this row survives the delete below and remains a legitimate,
    # permanent record that the account existed and was closed.
    await record_audit_event(db, actor_id=user.id, action="user.account_deleted", resource_type="user", resource_id=str(user.id))
    await delete_account(db, user)
    await db.commit()
    return MessageResponse(message="Your account and associated personal data have been deleted.")


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
                    is_email_verified=target.is_email_verified, is_active=target.is_active,
                    roles=[r.name for r in target.roles])
