from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.elimination import EliminationBattle, EliminationInvitation, EliminationParticipant
from app.models.user import User
from app.schemas.elimination import (
    BattleCreate,
    BattleOut,
    InvitationOut,
    InviteCreate,
    ParticipantOut,
    SubmitAnswerIn,
    SubmitAnswerOut,
)
from app.services.elimination_service import (
    create_battle,
    invite_to_battle,
    respond_to_invitation,
    start_battle,
    submit_answer,
)

router = APIRouter(prefix="/elimination", tags=["elimination"])


async def _require_battle_access(db: AsyncSession, battle: EliminationBattle, user: User) -> None:
    """Only the host or an accepted participant may view a battle's state —
    battle ids travel in notification links and browser history, so they
    are not secret the way a password is; this closes off a battle's
    participant names and live status to anyone who merely knows/guesses
    the UUID."""
    if user.id == battle.host_id:
        return
    is_participant = (await db.execute(
        select(EliminationParticipant.id).where(EliminationParticipant.battle_id == battle.id, EliminationParticipant.user_id == user.id)
    )).scalar_one_or_none()
    if is_participant is None:
        raise AuthorizationError("You're not part of this battle.")


@router.post("/battles", response_model=BattleOut, status_code=201)
async def create_elimination_battle(payload: BattleCreate, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await create_battle(db, user, payload.title, payload.topic_id)
    return battle


@router.get("/battles/me", response_model=list[BattleOut])
async def my_elimination_battles(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(EliminationBattle)
        .join(EliminationParticipant, EliminationParticipant.battle_id == EliminationBattle.id)
        .where(EliminationParticipant.user_id == user.id)
        .order_by(EliminationBattle.created_at.desc())
        .limit(50)
    )).scalars().all()
    return rows


@router.get("/battles/{battle_id}", response_model=BattleOut)
async def get_elimination_battle(battle_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    await _require_battle_access(db, battle, user)
    return battle


@router.get("/battles/{battle_id}/participants", response_model=list[ParticipantOut])
async def list_battle_participants(battle_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    await _require_battle_access(db, battle, user)
    rows = (await db.execute(
        select(EliminationParticipant, User.full_name)
        .join(User, User.id == EliminationParticipant.user_id)
        .where(EliminationParticipant.battle_id == battle_id)
    )).all()
    return [
        ParticipantOut(user_id=p.user_id, full_name=name, status=p.status, eliminated_at_round=p.eliminated_at_round, eliminated_reason=p.eliminated_reason)
        for p, name in rows
    ]


@router.post("/battles/{battle_id}/invite", response_model=InvitationOut, status_code=201)
async def invite_to_elimination_battle(battle_id: uuid.UUID, payload: InviteCreate, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    invitation = await invite_to_battle(db, battle, user, payload.invitee_id)
    return InvitationOut(
        id=invitation.id, battle_id=battle.id, battle_title=battle.title, inviter_id=invitation.inviter_id,
        inviter_name=user.full_name, invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at,
    )


@router.get("/invitations/incoming", response_model=list[InvitationOut])
async def list_incoming_invitations(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(EliminationInvitation, EliminationBattle.title, User.full_name)
        .join(EliminationBattle, EliminationBattle.id == EliminationInvitation.battle_id)
        .join(User, User.id == EliminationInvitation.inviter_id)
        .where(EliminationInvitation.invitee_id == user.id, EliminationInvitation.status == "pending")
        .order_by(EliminationInvitation.created_at.desc())
    )).all()
    return [
        InvitationOut(id=inv.id, battle_id=inv.battle_id, battle_title=title, inviter_id=inv.inviter_id, inviter_name=inviter_name, invitee_id=inv.invitee_id, status=inv.status, created_at=inv.created_at)
        for inv, title, inviter_name in rows
    ]


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationOut)
async def accept_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    invitation = await db.get(EliminationInvitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    battle = await db.get(EliminationBattle, invitation.battle_id)
    inviter = await db.get(User, invitation.inviter_id)
    invitation = await respond_to_invitation(db, invitation, user, accept=True)
    return InvitationOut(id=invitation.id, battle_id=invitation.battle_id, battle_title=battle.title if battle else "", inviter_id=invitation.inviter_id, inviter_name=inviter.full_name if inviter else "", invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at)


@router.post("/invitations/{invitation_id}/decline", response_model=InvitationOut)
async def decline_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    invitation = await db.get(EliminationInvitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    battle = await db.get(EliminationBattle, invitation.battle_id)
    inviter = await db.get(User, invitation.inviter_id)
    invitation = await respond_to_invitation(db, invitation, user, accept=False)
    return InvitationOut(id=invitation.id, battle_id=invitation.battle_id, battle_title=battle.title if battle else "", inviter_id=invitation.inviter_id, inviter_name=inviter.full_name if inviter else "", invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at)


@router.post("/battles/{battle_id}/start", response_model=BattleOut)
async def start_elimination_battle(battle_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    battle = await start_battle(db, battle, user)
    return battle


@router.post("/battles/{battle_id}/answer", response_model=SubmitAnswerOut)
async def submit_battle_answer(battle_id: uuid.UUID, payload: SubmitAnswerIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await submit_answer(db, battle_id, user, payload.selected_option_ids)
    return SubmitAnswerOut(**result)
