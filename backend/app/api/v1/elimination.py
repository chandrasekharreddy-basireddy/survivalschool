from __future__ import annotations

import io
import uuid

import qrcode
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_verified_user
from app.models.assessment import Question
from app.models.elimination import (
    EliminationAnswer,
    EliminationBattle,
    EliminationInvitation,
    EliminationParticipant,
    EliminationRound,
)
from app.models.user import Profile, User
from app.schemas.elimination import (
    BattleCreate,
    BattleOut,
    CurrentRoundOut,
    IntegrityViolationIn,
    IntegrityViolationOut,
    InvitationOut,
    InviteCreate,
    JoinByCodeIn,
    ParticipantOut,
    RoundOptionOut,
    RoundQuestionOut,
    SubmitAnswerIn,
    SubmitAnswerOut,
)
from app.services.elimination_service import (
    create_battle,
    invite_to_battle,
    join_battle_by_code,
    report_integrity_violation,
    respond_to_invitation,
    start_battle,
    submit_answer,
)

settings = get_settings()

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


async def _handle_for(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
    return profile.public_handle if profile else None


@router.post("/battles", response_model=BattleOut, status_code=201)
async def create_elimination_battle(payload: BattleCreate, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await create_battle(db, user, payload.title, payload.subject_name, payload.topic_name, payload.scheduled_start_at)
    return battle


@router.post("/battles/join", response_model=BattleOut, status_code=201)
async def join_elimination_battle_by_code(payload: JoinByCodeIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """The Free Fire-style room-code join — no invitation or connection
    required, unlike POST /battles/{id}/invite."""
    return await join_battle_by_code(db, user, payload.code)


@router.get("/battles/{battle_id}/qr", response_class=Response)
async def elimination_battle_join_qr(battle_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    await _require_battle_access(db, battle, user)
    join_url = f"{settings.FRONTEND_URL}/elimination/join/{battle.join_code}"
    image = qrcode.make(join_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


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
        select(EliminationParticipant, User.full_name, Profile.public_handle)
        .join(User, User.id == EliminationParticipant.user_id)
        .outerjoin(Profile, Profile.user_id == EliminationParticipant.user_id)
        .where(EliminationParticipant.battle_id == battle_id)
    )).all()
    return [
        ParticipantOut(user_id=p.user_id, full_name=name, public_handle=handle, status=p.status, eliminated_at_round=p.eliminated_at_round, eliminated_reason=p.eliminated_reason)
        for p, name, handle in rows
    ]


@router.get("/battles/{battle_id}/round", response_model=CurrentRoundOut | None)
async def get_current_round(battle_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    """REST fallback for the active round — the websocket only ever
    broadcasts battle.round_released once, at the moment it happens; a
    client that connects afterward (a page refresh mid-round, a dropped
    connection, backgrounding the tab) has no other way to learn what the
    current question even is. Returns null when there's no unresolved
    round right now (lobby, between rounds, or completed)."""
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    await _require_battle_access(db, battle, user)

    round_ = (await db.execute(
        select(EliminationRound)
        .where(EliminationRound.battle_id == battle_id, EliminationRound.resolved_at.is_(None))
        .order_by(EliminationRound.round_number.desc())
        .limit(1)
    )).scalar_one_or_none()
    if round_ is None:
        return None

    question = (await db.execute(
        select(Question).where(Question.id == round_.question_id).options(selectinload(Question.options))
    )).scalar_one()

    participant = (await db.execute(
        select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.user_id == user.id)
    )).scalar_one_or_none()
    my_answer = None
    if participant is not None:
        my_answer = (await db.execute(
            select(EliminationAnswer).where(EliminationAnswer.round_id == round_.id, EliminationAnswer.participant_id == participant.id)
        )).scalar_one_or_none()

    return CurrentRoundOut(
        round_number=round_.round_number, deadline_at=round_.deadline_at,
        question=RoundQuestionOut(
            id=question.id, prompt=question.prompt, question_type=question.question_type,
            options=[RoundOptionOut(id=o.id, text=o.text) for o in question.options],
        ),
        already_answered=my_answer is not None,
        my_is_correct=my_answer.is_correct if my_answer else None,
    )


@router.post("/battles/{battle_id}/invite", response_model=InvitationOut, status_code=201)
async def invite_to_elimination_battle(battle_id: uuid.UUID, payload: InviteCreate, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None:
        raise NotFoundError("Battle not found.")
    invitation = await invite_to_battle(db, battle, user, payload.invitee_id)
    return InvitationOut(
        id=invitation.id, battle_id=battle.id, battle_title=battle.title, inviter_id=invitation.inviter_id,
        inviter_name=user.full_name, inviter_handle=await _handle_for(db, user.id),
        invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at,
    )


@router.get("/invitations/incoming", response_model=list[InvitationOut])
async def list_incoming_invitations(user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(EliminationInvitation, EliminationBattle.title, User.full_name, Profile.public_handle)
        .join(EliminationBattle, EliminationBattle.id == EliminationInvitation.battle_id)
        .join(User, User.id == EliminationInvitation.inviter_id)
        .outerjoin(Profile, Profile.user_id == EliminationInvitation.inviter_id)
        .where(EliminationInvitation.invitee_id == user.id, EliminationInvitation.status == "pending")
        .order_by(EliminationInvitation.created_at.desc())
    )).all()
    return [
        InvitationOut(id=inv.id, battle_id=inv.battle_id, battle_title=title, inviter_id=inv.inviter_id, inviter_name=inviter_name, inviter_handle=handle, invitee_id=inv.invitee_id, status=inv.status, created_at=inv.created_at)
        for inv, title, inviter_name, handle in rows
    ]


@router.post("/invitations/{invitation_id}/accept", response_model=InvitationOut)
async def accept_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    invitation = await db.get(EliminationInvitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    battle = await db.get(EliminationBattle, invitation.battle_id)
    inviter = await db.get(User, invitation.inviter_id)
    invitation = await respond_to_invitation(db, invitation, user, accept=True)
    return InvitationOut(id=invitation.id, battle_id=invitation.battle_id, battle_title=battle.title if battle else "", inviter_id=invitation.inviter_id, inviter_name=inviter.full_name if inviter else "", inviter_handle=await _handle_for(db, invitation.inviter_id), invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at)


@router.post("/invitations/{invitation_id}/decline", response_model=InvitationOut)
async def decline_invitation(invitation_id: uuid.UUID, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    invitation = await db.get(EliminationInvitation, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    battle = await db.get(EliminationBattle, invitation.battle_id)
    inviter = await db.get(User, invitation.inviter_id)
    invitation = await respond_to_invitation(db, invitation, user, accept=False)
    return InvitationOut(id=invitation.id, battle_id=invitation.battle_id, battle_title=battle.title if battle else "", inviter_id=invitation.inviter_id, inviter_name=inviter.full_name if inviter else "", inviter_handle=await _handle_for(db, invitation.inviter_id), invitee_id=invitation.invitee_id, status=invitation.status, created_at=invitation.created_at)


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


@router.post("/battles/{battle_id}/integrity-violation", response_model=IntegrityViolationOut)
async def report_battle_integrity_violation(battle_id: uuid.UUID, payload: IntegrityViolationIn, user: User = Depends(get_current_verified_user), db: AsyncSession = Depends(get_db)):
    result = await report_integrity_violation(db, battle_id, user, payload.violation_type)
    return IntegrityViolationOut(**result)
