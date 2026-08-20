"""Elimination battle state machine — the whole point of this module is
that the browser is a display/input device only. Every decision (is this
answer correct, has the 15-second window expired, who's eliminated, who
won) is made here against durable Postgres rows and a Redis-coordinated
sweep, never trusted from a client request.

Round lifecycle:
  release_round() creates an EliminationRound with deadline_at fixed at
  creation time and broadcasts the question over the battle's websocket
  channel — clients get only the current question, never future ones
  (each round is a fresh row; there is no "next question" endpoint that
  could be probed ahead of time).

  submit_answer() grades and idempotently records one EliminationAnswer per
  (round, participant) — a wrong answer eliminates the participant
  immediately (no need to wait for the round to end when the answer is
  already know to be wrong). A correct answer just marks the round-level
  answer row; the participant only formally "survives" once the round
  resolves.

  A round resolves either the instant every still-active participant has
  answered (checked at the end of every submit_answer call, so "no
  artificial waiting period" for a fast-finishing round — spec section 21),
  or when its deadline passes, whichever comes first — enforced by
  elimination_sweep_loop below, a *separate, tight* loop from the 60s
  scheduler_runtime.py tick (that cadence is far too coarse against a
  strict 15-second deadline; a naive add-on there could miss/delay
  elimination by up to 59 seconds — see scheduler_runtime.py's own
  docstring on TICK_SECONDS). resolve_round() auto-eliminates anyone who
  never submitted (reason="timeout"), then either declares a winner (one
  active participant left), ends the battle with no winner (zero left —
  a rare simultaneous-elimination edge case), or releases the next round.

  Every battle-scoped mutation runs under a Redis lock keyed by battle id
  (services/distributed_lock.py) so two gunicorn workers can't both try to
  resolve/advance the same round concurrently — without it, a submit
  landing on worker A at the exact moment the sweep on worker B decides
  the deadline passed could both release round N+1, producing two
  question sets in flight for the same battle.
"""
from __future__ import annotations

import asyncio
import contextlib
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationAppError
from app.database import AsyncSessionLocal
from app.models.assessment import Question
from app.models.elimination import (
    QUESTION_DEADLINE_SECONDS,
    EliminationAnswer,
    EliminationBattle,
    EliminationInvitation,
    EliminationParticipant,
    EliminationRound,
)
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.distributed_lock import try_lock
from app.services.notification_service import create_notification
from app.services.scoring_service import grade_answer
from app.services.social_graph_service import has_accepted_connection
from app.websockets.manager import manager as ws_manager

logger = structlog.get_logger("survivalschool.elimination")

SWEEP_INTERVAL_SECONDS = 2
MAX_INVITEES_PER_BATTLE = 50
# Excludes visually ambiguous characters (0/O, 1/I/L) since this is meant to
# be read off a phone screen or typed in by hand, not just scanned as a QR.
_JOIN_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_JOIN_CODE_LENGTH = 6


def _battle_lock_key(battle_id: uuid.UUID) -> str:
    return f"elimination:battle:{battle_id}:leader"


async def _battle_channel(battle_id: uuid.UUID) -> uuid.UUID:
    # The websocket connection manager keys rooms by a single UUID — reuse
    # the battle id directly as its own "room id" rather than a parallel
    # mapping table.
    return battle_id


def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(_JOIN_CODE_LENGTH))


async def create_battle(db: AsyncSession, host: User, title: str, topic_id: uuid.UUID) -> EliminationBattle:
    battle = EliminationBattle(host_id=host.id, title=title, topic_id=topic_id, status="lobby", join_code=_generate_join_code())
    # Collisions are astronomically unlikely at this alphabet/length (32^6 ≈
    # 1.07B combinations) but the unique constraint plus a bounded retry
    # loop makes this correct rather than merely probably-fine.
    for _ in range(5):
        try:
            async with db.begin_nested():
                db.add(battle)
                await db.flush()
            break
        except IntegrityError:
            battle.join_code = _generate_join_code()
    else:
        raise ConflictError("Couldn't allocate a battle room code — please try again.")
    db.add(EliminationParticipant(battle_id=battle.id, user_id=host.id, status="ready"))
    await record_audit_event(db, actor_id=host.id, action="elimination.battle_created", resource_type="elimination_battle", resource_id=str(battle.id))
    await db.commit()
    await db.refresh(battle)
    return battle


async def join_battle_by_code(db: AsyncSession, user: User, code: str) -> EliminationBattle:
    """The Free Fire-style path: anyone holding the room code joins
    directly, no invitation or prior connection required — that's the
    whole point of a shareable code over the connections-gated invite flow
    in invite_to_battle() below."""
    battle = (await db.execute(
        select(EliminationBattle).where(EliminationBattle.join_code == code.strip().upper())
    )).scalar_one_or_none()
    if battle is None:
        raise NotFoundError("No battle found with that code.")
    if battle.status != "lobby":
        raise ConflictError("This battle has already started or finished.")

    existing = (await db.execute(
        select(EliminationParticipant).where(EliminationParticipant.battle_id == battle.id, EliminationParticipant.user_id == user.id)
    )).scalar_one_or_none()
    if existing is not None:
        return battle

    participant_count = (await db.execute(
        select(EliminationParticipant.id).where(EliminationParticipant.battle_id == battle.id)
    )).scalars().all()
    if len(participant_count) >= MAX_INVITEES_PER_BATTLE + 1:
        raise ConflictError(f"This battle is full ({MAX_INVITEES_PER_BATTLE + 1} players max).")

    db.add(EliminationParticipant(battle_id=battle.id, user_id=user.id, status="ready"))
    await db.commit()
    return battle


async def invite_to_battle(db: AsyncSession, battle: EliminationBattle, inviter: User, invitee_id: uuid.UUID) -> EliminationInvitation:
    if battle.status != "lobby":
        raise ConflictError("This battle has already started — you can't invite anyone else.")
    if inviter.id != battle.host_id:
        raise AuthorizationError("Only the host can invite people to this battle.")
    if invitee_id == inviter.id:
        raise ValidationAppError("You can't invite yourself.")
    invitee = await db.get(User, invitee_id)
    if invitee is None or invitee.deleted_at is not None:
        raise NotFoundError("User not found.")
    if not await has_accepted_connection(db, inviter.id, invitee_id):
        raise AuthorizationError("You can only invite people you're connected with — share the room code/QR instead to invite anyone else.")

    existing_count = (await db.execute(
        select(EliminationInvitation).where(EliminationInvitation.battle_id == battle.id)
    )).scalars().all()
    if len(existing_count) >= MAX_INVITEES_PER_BATTLE:
        raise ConflictError(f"This battle already has the maximum of {MAX_INVITEES_PER_BATTLE} invitations.")

    existing = (await db.execute(
        select(EliminationInvitation).where(EliminationInvitation.battle_id == battle.id, EliminationInvitation.invitee_id == invitee_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    invitation = EliminationInvitation(battle_id=battle.id, inviter_id=inviter.id, invitee_id=invitee_id)
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    await create_notification(
        db, user=invitee, category="battle", title=f"{inviter.full_name} invited you to an elimination battle",
        body=battle.title, link_url=f"/elimination/{battle.id}",
    )
    await db.commit()
    return invitation


async def respond_to_invitation(db: AsyncSession, invitation: EliminationInvitation, user: User, accept: bool) -> EliminationInvitation:
    if invitation.invitee_id != user.id:
        raise NotFoundError("Invitation not found.")
    if invitation.status != "pending":
        raise ConflictError(f"This invitation was already {invitation.status}.")
    invitation.status = "accepted" if accept else "declined"
    invitation.responded_at = datetime.now(UTC)
    if accept:
        battle = await db.get(EliminationBattle, invitation.battle_id)
        if battle is not None and battle.status == "lobby":
            existing_participant = (await db.execute(
                select(EliminationParticipant).where(EliminationParticipant.battle_id == battle.id, EliminationParticipant.user_id == user.id)
            )).scalar_one_or_none()
            if existing_participant is None:
                db.add(EliminationParticipant(battle_id=battle.id, user_id=user.id, status="ready"))
    await db.commit()
    await db.refresh(invitation)
    return invitation


async def _pick_question(db: AsyncSession, topic_id: uuid.UUID, exclude_ids: set[uuid.UUID]) -> Question | None:
    rows = (await db.execute(
        select(Question.id).where(Question.topic_id == topic_id, Question.is_validated.is_(True))
    )).scalars().all()
    candidates = [q for q in rows if q not in exclude_ids]
    if not candidates:
        return None
    # Eager-load options here, not via db.get()'s default lazy relationship —
    # release_round() below reads question.options *after* a db.commit(),
    # which expires the instance by default (expire_on_commit=True). Async
    # SQLAlchemy has no implicit lazy-load fallback the way sync mode does;
    # touching an unloaded relationship post-commit raises MissingGreenlet
    # instead of transparently re-querying. Loading it up front avoids that.
    return (await db.execute(
        select(Question).where(Question.id == random.choice(candidates)).options(selectinload(Question.options))
    )).scalar_one()


async def release_round(db: AsyncSession, battle: EliminationBattle) -> EliminationRound | None:
    used_question_ids = {
        uuid.UUID(str(r.question_id)) for r in (await db.execute(
            select(EliminationRound.question_id).where(EliminationRound.battle_id == battle.id)
        )).all()
    }
    question = await _pick_question(db, battle.topic_id, used_question_ids)
    if question is None:
        logger.warning("elimination_no_more_questions", battle_id=str(battle.id))
        return None

    now = datetime.now(UTC)
    round_number = battle.current_round_number + 1
    round_ = EliminationRound(
        battle_id=battle.id, round_number=round_number, question_id=question.id,
        deadline_at=now + timedelta(seconds=QUESTION_DEADLINE_SECONDS),
    )
    db.add(round_)
    battle.current_round_number = round_number
    await db.commit()
    await db.refresh(round_)

    options_out = [{"id": str(o.id), "text": o.text} for o in question.options]
    await ws_manager.broadcast(await _battle_channel(battle.id), {
        "event": "battle.round_released", "battle_id": str(battle.id), "round_number": round_number,
        "question": {"id": str(question.id), "prompt": question.prompt, "question_type": question.question_type, "options": options_out},
        "deadline_at": round_.deadline_at.isoformat(),
    })
    return round_


async def start_battle(db: AsyncSession, battle: EliminationBattle, host: User) -> EliminationBattle:
    if host.id != battle.host_id:
        raise AuthorizationError("Only the host can start this battle.")
    if battle.status != "lobby":
        raise ConflictError("This battle has already started.")
    participants = (await db.execute(select(EliminationParticipant).where(EliminationParticipant.battle_id == battle.id))).scalars().all()
    if len(participants) < 2:
        raise ValidationAppError("At least one other player needs to accept an invitation before you can start.")

    for p in participants:
        p.status = "active"
    battle.status = "active"
    battle.started_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(battle)

    await ws_manager.broadcast(await _battle_channel(battle.id), {"event": "battle.started", "battle_id": str(battle.id)})
    round_ = await release_round(db, battle)
    if round_ is None:
        # No question bank for this topic — cannot run the battle. Rare
        # (blocked earlier normally by the create-battle flow validating
        # the topic has questions), but fail closed rather than leave
        # participants stuck in "active" with no question ever coming.
        battle.status = "cancelled"
        await db.commit()
        raise ValidationAppError("No questions are available for this topic yet — the battle was cancelled.")
    return battle


async def submit_answer(db: AsyncSession, battle_id: uuid.UUID, user: User, selected_option_ids: list[uuid.UUID]) -> dict:
    async with try_lock(_battle_lock_key(battle_id), ttl_seconds=10) as got_lock:
        if not got_lock:
            # Another worker is mid-resolve for this exact battle (e.g. the
            # sweep loop just grabbed the lock at the same instant this
            # request arrived). Reject rather than silently no-op — the
            # client's retry logic will re-send and land after resolution.
            raise ConflictError("This battle is being updated — try again in a moment.")

        battle = await db.get(EliminationBattle, battle_id)
        if battle is None or battle.status != "active":
            raise NotFoundError("Battle not found or not active.")
        participant = (await db.execute(
            select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.user_id == user.id)
        )).scalar_one_or_none()
        if participant is None:
            raise NotFoundError("You're not a participant in this battle.")
        if participant.status != "active":
            raise ConflictError("You've already been eliminated from this battle.")

        round_ = (await db.execute(
            select(EliminationRound).where(EliminationRound.battle_id == battle_id, EliminationRound.round_number == battle.current_round_number)
        )).scalar_one_or_none()
        if round_ is None:
            raise NotFoundError("No active round.")
        now = datetime.now(UTC)
        if now > round_.deadline_at:
            raise ConflictError("The deadline for this question has already passed.")

        existing_answer = (await db.execute(
            select(EliminationAnswer).where(EliminationAnswer.round_id == round_.id, EliminationAnswer.participant_id == participant.id)
        )).scalar_one_or_none()
        if existing_answer is not None:
            # Idempotent: a retried/duplicated submit is a safe no-op, not a
            # second grading pass.
            return {"is_correct": existing_answer.is_correct, "eliminated": participant.status == "eliminated"}

        question = (await db.execute(
            select(Question).where(Question.id == round_.question_id).options(selectinload(Question.options))
        )).scalar_one()
        is_correct, _points = grade_answer(question, [str(i) for i in selected_option_ids], None)
        db.add(EliminationAnswer(round_id=round_.id, participant_id=participant.id, selected_option_ids=[str(i) for i in selected_option_ids], is_correct=is_correct))

        if not is_correct:
            participant.status = "eliminated"
            participant.eliminated_at_round = round_.round_number
            participant.eliminated_reason = "wrong_answer"
        await db.commit()

        await ws_manager.broadcast(await _battle_channel(battle_id), {
            "event": "battle.answer_result", "battle_id": str(battle_id), "user_id": str(user.id),
            "round_number": round_.round_number, "is_correct": is_correct,
        })

        # Early-resolve once every still-active participant has answered
        # this round — "no artificial waiting period between rounds."
        active_participants = (await db.execute(
            select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.status == "active")
        )).scalars().all()
        answered_participant_ids = set((await db.execute(
            select(EliminationAnswer.participant_id).where(EliminationAnswer.round_id == round_.id)
        )).scalars().all())
        if all(p.id in answered_participant_ids for p in active_participants):
            await resolve_round(db, battle_id, round_.id)

        return {"is_correct": is_correct, "eliminated": not is_correct}


async def resolve_round(db: AsyncSession, battle_id: uuid.UUID, round_id: uuid.UUID) -> None:
    """Not itself lock-guarded — callers (submit_answer's early-resolve
    path, and the sweep loop) already hold the battle lock when they call
    this."""
    round_ = await db.get(EliminationRound, round_id)
    if round_ is None or round_.resolved_at is not None:
        return
    battle = await db.get(EliminationBattle, battle_id)
    if battle is None or battle.status != "active":
        return

    active_participants = (await db.execute(
        select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.status == "active")
    )).scalars().all()
    answered_ids = set((await db.execute(
        select(EliminationAnswer.participant_id).where(EliminationAnswer.round_id == round_.id)
    )).scalars().all())

    eliminated_this_round = []
    for p in active_participants:
        if p.id not in answered_ids:
            p.status = "eliminated"
            p.eliminated_at_round = round_.round_number
            p.eliminated_reason = "timeout"
            eliminated_this_round.append(p)

    round_.resolved_at = datetime.now(UTC)
    survivors = (await db.execute(
        select(EliminationParticipant).where(EliminationParticipant.battle_id == battle_id, EliminationParticipant.status == "active")
    )).scalars().all()

    await ws_manager.broadcast(await _battle_channel(battle_id), {
        "event": "battle.round_resolved", "battle_id": str(battle_id), "round_number": round_.round_number,
        "eliminated_user_ids": [str(p.user_id) for p in eliminated_this_round], "survivors_remaining": len(survivors),
    })

    if len(survivors) <= 1:
        winner = survivors[0] if survivors else None
        if winner is not None:
            winner.status = "winner"
            battle.winner_id = winner.user_id
        battle.status = "completed"
        battle.ended_at = datetime.now(UTC)
        await db.commit()
        await ws_manager.broadcast(await _battle_channel(battle_id), {
            "event": "battle.completed", "battle_id": str(battle_id),
            "winner_user_id": str(winner.user_id) if winner else None,
        })
        if winner is not None:
            winner_user = await db.get(User, winner.user_id)
            if winner_user is not None:
                await create_notification(db, user=winner_user, category="battle", title="You won the elimination battle!", body=battle.title, link_url=f"/elimination/{battle.id}")
                await db.commit()
        return

    await db.commit()
    await release_round(db, battle)


async def _sweep_once() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        overdue_rounds = (await db.execute(
            select(EliminationRound).where(EliminationRound.resolved_at.is_(None), EliminationRound.deadline_at < now)
        )).scalars().all()
        for round_ in overdue_rounds:
            async with try_lock(_battle_lock_key(round_.battle_id), ttl_seconds=10) as got_lock:
                if not got_lock:
                    continue
                await resolve_round(db, round_.battle_id, round_.id)


async def elimination_sweep_loop(stop: asyncio.Event) -> None:
    """A separate, tight loop from scheduler_runtime.py's 60s tick — see
    this module's docstring for why that cadence can't serve a strict
    15-second deadline. Runs unconditionally on every worker; the
    per-battle Redis lock (not a single global leader lock) is what keeps
    concurrent workers from double-resolving the same round, so this scales
    with however many battles are active rather than bottlenecking on one
    process."""
    logger.info("elimination_sweep_loop_started", interval_seconds=SWEEP_INTERVAL_SECONDS)
    while not stop.is_set():
        try:
            await _sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("elimination_sweep_failed", exc_info=True)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=SWEEP_INTERVAL_SECONDS)
    logger.info("elimination_sweep_loop_stopped")
